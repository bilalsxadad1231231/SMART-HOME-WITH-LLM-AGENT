import logging
import json
from flask import Flask, request, jsonify
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from typing import Dict, Any
from groq_client import GroqLLM
from langchain_community.llms import ollama
from prompt_template import template_1, template_2,template_3
import serial
import csv
import io
import threading
import time

class SmartHomeController:
    def __init__(self, 
                 serial_port='COM5', 
                 baud_rate=9600, 
                 groq_api_key="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"):
        """
        Initialize Smart Home Controller with serial and Langchain components
        """
        # Device State Dictionary
        self.device_states = {
            # Lights
            "room 1 light": "off",
            "room 2 light": "off",
            "room 3 light": "off",
            "kitchen light": "off",
            
            # Fans
            "room 1 fan": "off",
            "room 2 fan": "off",
            "room 3 fan": "off",
            "kitchen fan": "off"
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
        
        # Define response schemas for structured output parsing
# Update response schemas to include delay_seconds
        response_schemas = [
            ResponseSchema(
                name="device_states", 
                description="Dictionary of device names and their states (on/off)"
            ),
            ResponseSchema(
                name="chatbot_message", 
                description="Friendly message describing the actions taken"
            ),
            ResponseSchema(
                name="delay_seconds", 
                description="Optional delay (in seconds) before processing the command. Default to 0 if not specified."
            )
        ]

        
        self.output_parser = StructuredOutputParser.from_response_schemas(response_schemas)
        
        # Create prompt template with output parser instructions
        template = template_3
        
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
            parsed_output = self.output_parser.parse(result)
            
            # Update device states from parsed output
            device_states = parsed_output.get("device_states", {})
            for device, state in device_states.items():
                if device in self.device_states:
                    self.device_states[device] = state
            
            # Default to 0 delay if not provided
            delay = parsed_output.get("delay_seconds", 0)
            
            return {
                "device_states": device_states,
                "chatbot_message": parsed_output.get("chatbot_message", "Command processed"),
                "delay_seconds": delay
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
                
            for dev, dev_state in self.device_states.items():
                # Prepare CSV output
                output = io.StringIO()
                csv_writer = csv.writer(output, delimiter=',')
                csv_writer.writerow([dev, dev_state])
                
                # Send message with markers
                message = f"START{output.getvalue().strip()}END\n"
                self.ser.write(message.encode('utf-8'))
                print(f"Sent device state: {dev} = {dev_state}")
                
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
    Create Flask application with voice command endpoint
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
            else:
                return jsonify({
                    'status': 'error', 
                    'message': 'Unable to parse command'
                })
        
        return jsonify({
            'status': 'error', 
            'message': 'No command received'
        })
        
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