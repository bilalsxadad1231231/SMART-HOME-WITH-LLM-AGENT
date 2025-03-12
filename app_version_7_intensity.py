import logging
import json
from flask import Flask, request, jsonify
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from typing import Dict, Any
from groq_client import GroqLLM
from langchain_community.llms import ollama
import serial
import csv
import io
import threading
import time
from prompt_template import template_5, template_7

class SmartHomeController:
    def __init__(self, 
                 serial_port='COM5', 
                 baud_rate=9600, 
                 groq_api_key="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"):
        """
        Initialize Smart Home Controller with serial and Langchain components
        """
        # Updated Device State Dictionary
        self.device_states = {
            # Lights with ON/OFF and Intensity Control
            "room 1 light": "off",
            "room 2 light": {"state": "off", "intensity": 0},  # Intensity control (0-100%)
            "room 3 light": {"state": "off", "intensity": 0},  # Intensity control (0-100%)
            "room 4 light": "off",
            "kitchen light": "off",
            
            # TV and Refrigerator (ON/OFF)
            "TV": "off",
            "Refrigerator": "off",

            # DC Motor (ON/OFF)
            "DC motor": "off",

            # Servo Motor (Clockwise/Anticlockwise in degrees)
            "Servo motor": {"direction": "none", "degrees": 0}
        }

        # Serial Communication Setup
        try:
            self.ser = serial.Serial(
                port=serial_port, 
                baudrate=baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            print(f"Connected to serial port: {serial_port}")
            self.ser.close()
            time.sleep(2)  # Allow microcontroller to reset
        except serial.SerialException as e:
            print(f"Error connecting to serial port: {e}")
            self.ser = None

        # Initialize Langchain components
        self.llm = GroqLLM(
            groq_api_key=groq_api_key,
            model_name="llama-3.3-70b-versatile"
        )
        
        # Updated response schemas
        response_schemas = [
            ResponseSchema(
                name="device_states", 
                description="Dictionary containing device names as keys and their respective states as values for the effected devices."
            ),
            ResponseSchema(
                name="light_intensity", 
                description="Dictionary of lights with adjustable intensity levels (0-100). Only applies to 'room 2 light' and 'room 3 light'."
            ),
            ResponseSchema(
                name="servo_motor_angle", 
                description="Angle in degrees for the servo motor (0-180)."
            ),
            ResponseSchema(
                name="servo_motor_direction", 
                description="Direction of servo motor rotation. Must be one of: 'clock', 'anti', or 'none'."
            ),
            ResponseSchema(
                name="chatbot_message", 
                description="Friendly message describing the actions taken."
            ),
            ResponseSchema(
                name="delay_seconds", 
                description="Optional delay (in seconds) before processing the command. Defaults to 0 if not specified."
            )
        ]
        
        self.output_parser = StructuredOutputParser.from_response_schemas(response_schemas)
        
        # Create prompt template with output parser instructions
        template = template_5  # Using the new template provided
        
        prompt = PromptTemplate(
            template=template,
            input_variables=["command"],
            partial_variables={"format_instructions": self.output_parser.get_format_instructions()}
        )
        
        # Create Langchain chain
        self.chain = LLMChain(llm=self.llm, prompt=prompt)

    def parse_command(self, command: str) -> Dict[str, Any]:
        try:
            result = self.chain.run(command=command)
            print(result)
            parsed_output = self.output_parser.parse(result)
            
            # Update device states from parsed output
            device_states = parsed_output.get("device_states", {})
            light_intensity = parsed_output.get("light_intensity", {})
            servo_motor_angle = parsed_output.get("servo_motor_angle", None)
            servo_motor_direction = parsed_output.get("servo_motor_direction", None)
            
            # Update device states
            for device, state in device_states.items():
                if device in self.device_states:
                    if device in ["room 2 light", "room 3 light"]:
                        # Handle intensity-controlled lights
                        if isinstance(self.device_states[device], dict):
                            if isinstance(state, dict):
                                # If state is a dict, update both state and intensity
                                self.device_states[device]["state"] = state.get("state", self.device_states[device]["state"])
                                self.device_states[device]["intensity"] = state.get("intensity", self.device_states[device]["intensity"])
                            else:
                                # If state is a string (e.g., "on" or "off"), update only the state
                                self.device_states[device]["state"] = state
                    elif device == "Servo motor":
                        # Handle servo motor
                        if isinstance(state, dict):
                            self.device_states[device]["direction"] = state.get("direction", self.device_states[device]["direction"])
                            self.device_states[device]["degrees"] = state.get("degrees", self.device_states[device]["degrees"])
                    else:
                        # Handle simple on/off devices
                        self.device_states[device] = state
            
            # Update light intensities if provided
            for light, intensity in light_intensity.items():
                if light in ["room 2 light", "room 3 light"]:
                    # Remove percentage sign if present and convert to integer
                    if isinstance(intensity, str):
                        intensity = intensity.rstrip('%')
                    try:
                        self.device_states[light]["intensity"] = int(intensity)
                        # If intensity is being set, ensure the light is on
                        if int(intensity) > 0:
                            self.device_states[light]["state"] = "on"
                        else:
                            self.device_states[light]["state"] = "off"
                    except (ValueError, TypeError):
                        logging.error(f"Invalid intensity value: {intensity}")
            
            # Update servo motor properties if provided
            if servo_motor_angle is not None:
                try:
                    self.device_states["Servo motor"]["degrees"] = int(str(servo_motor_angle).rstrip('°'))
                except (ValueError, TypeError):
                    logging.error(f"Invalid servo angle value: {servo_motor_angle}")
                    
            if servo_motor_direction is not None:
                self.device_states["Servo motor"]["direction"] = servo_motor_direction
            
            return {
                "device_states": self.device_states,
                "chatbot_message": parsed_output.get("chatbot_message", "Command processed"),
                "delay_seconds": int(parsed_output.get("delay_seconds", 0))
            }
            
        except Exception as e:
            logging.error(f"Command parsing error: {e}")
            return None

    def send_device_states(self):
        """
        Send device states to microcontroller sequentially
        """
        try:
            if not self.ser.is_open:
                self.ser.open()
                
            for dev, state in self.device_states.items():
                # Prepare CSV output
                output = io.StringIO()
                csv_writer = csv.writer(output, delimiter=',')
                
                if isinstance(state, dict):
                    if dev in ["room 2 light", "room 3 light"]:
                        # Send light state and intensity
                        csv_writer.writerow([dev, state["state"], state["intensity"]])
                    elif dev == "Servo motor":
                        # Send servo motor direction and degrees
                        csv_writer.writerow([dev, state["direction"], state["degrees"]])
                else:
                    # Send simple on/off state
                    csv_writer.writerow([dev, state])
                
                # Send message with markers
                message = f"START{output.getvalue().strip()}END\n"
                self.ser.write(message.encode('utf-8'))
                # print(message)
                # print(f"Sent device state: {dev} = {state}")
                # self.wait_for_ack()
                time.sleep(0.3)
            
            return True
            
        except Exception as e:
            logging.error(f"Error sending device states: {e}")
            return False

    def wait_for_ack(self):
        """Wait for acknowledgment from the microcontroller"""
        try:
            start_time = time.time()
            while time.time() - start_time < 2:
                if self.ser.in_waiting:
                    response = self.ser.readline().decode('utf-8').strip()
                    print(f"Received: {response}")
                    return
            print("No acknowledgment received")
        except Exception as e:
            print(f"Error waiting for acknowledgment: {e}")

    def close(self):
        """Close serial connection"""
        if self.ser:
            self.ser.close()
            print("Serial connection closed")


def create_flask_app(controller):
    """
    Create Flask application with voice command and direct command endpoints
    """
    app = Flask(__name__)
    
    @app.route('/voice-command', methods=['POST'])
    def receive_voice_command():
        command = request.form.get('command', '')
        
        if command:
            parsed_result = controller.parse_command(command)
            
            if parsed_result:
                delay_seconds = int(parsed_result.get("delay_seconds", 0))
                if delay_seconds > 0:
                    # Schedule sending device states after the delay
                    threading.Timer(delay_seconds, controller.send_device_states).start()
                    print(f"Command scheduled to execute after {delay_seconds} seconds.")
                else:
                    # Execute immediately in a separate thread
                    threading.Thread(target=controller.send_device_states, daemon=True).start()
                    
                return jsonify({
                    'status': 'success', 
                    'message': parsed_result['chatbot_message'],
                    'device_states': controller.device_states
                })
        
        return jsonify({
            'status': 'error', 
            'message': 'No command received'
        })

    @app.route('/command', methods=['POST'])
    def receive_direct_command():
        try:
            new_states = request.get_json()
            print(new_states)
            if not new_states:
                return jsonify({
                    'status': 'error',
                    'message': 'No state data received'
                }), 400
            # Directly replace the device states
            controller.device_states = new_states
            
            # Send updated states to Arduino
            threading.Thread(target=controller.send_device_states, daemon=True).start()
            
            return jsonify({
                'status': 'success',
                'message': 'Device states updated',
                'device_states': controller.device_states
            })

        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'Error processing command: {str(e)}'
            }), 500
    
    return app

def main():
    """
    Main application entry point
    """
    try:
        # Initialize Smart Home Controller
        controller = SmartHomeController()
        
        # Create and run Flask app
        app = create_flask_app(controller)
        app.run(host='0.0.0.0', port=5000, debug=True)

    except Exception as e:
        print(f"Fatal error: {e}")
    finally:
        if 'controller' in locals():
            controller.close()

if __name__ == "__main__":
    main()