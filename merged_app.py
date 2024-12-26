import serial
import csv
import io
import time
import logging
from flask import Flask, request, jsonify
from huggingface_hub import InferenceClient



class SmartHomeController:
    def __init__(self, 
                 serial_port='COM5', 
                 baud_rate=9600, 
                 hf_api_key="YOUR HUGGING FACE API KEY"):
        """
        Initialize Smart Home Controller with serial and HuggingFace client
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

        # HuggingFace Inference Client
        self.hf_client = InferenceClient(api_key=hf_api_key)

    def parse_command(self, command):
        """
        Parse command using HuggingFace model to extract device states
        """

        prompt = """
        You are a friendly assistant that extracts light and fan control details from user commands and converts them into a strict JSON format. Additionally, you generate a friendly response summarizing the changes made.

Description:
I have the following devices:
- Lights: "room 1 light," "room 2 light," "room 3 light," "kitchen light."
- Fans: "room 1 fan," "room 2 fan," "room 3 fan," "kitchen fan."

Extraction Rules:
- Identify lights and fans by their unique identifiers (e.g., "room 1 light," "kitchen fan").
- Use `on` for "turn on" or "on."
- Use `off` for "turn off" or "off."
- Output must be a valid JSON string.
- Include a `chatbot message` field in the JSON to provide a friendly response summarizing the changes.
- Only include devices explicitly mentioned in the command.
- The output must strictly follow this format:
   - Valid JSON with keys for the devices and their states (`on` or `off`).
   - A `chatbot message` field summarizing the changes in a friendly manner.
   - No additional text outside the JSON structure.

Strict Examples:
- Input: "Turn on room 1 light and off kitchen fan"
  Output: {"room 1 light": "on", "kitchen fan": "off", "chatbot message": "Okay, I have turned on the room 1 light and turned off the kitchen fan for you."}
- Input: "Switch off room 2 light and room 2 fan"
  Output: {"room 2 light": "off", "room 2 fan": "off", "chatbot message": "Got it, I have turned off the room 2 light and fan for you."}
- Input: "Turn on kitchen light and room 3 fan"
  Output: {"kitchen light": "on", "room 3 fan": "on", "chatbot message": "Sure, I have turned on the kitchen light and room 3 fan for you."}
- Input: "Switch off all lights in room 1 and room 2"
  Output: {"room 1 light": "off", "room 2 light": "off", "chatbot message": "Done! All lights in room 1 and room 2 have been turned off."}

Now, extract the details, generate the JSON string for this command, and include a friendly chatbot message:

Input: {input}
Output:
"""

        messages = [
            {
                "role": "user",
                "content": prompt.replace("{input}",command)
            }
        ]

        try:
            completion = self.hf_client.chat.completions.create(
                model="Qwen/Qwen2.5-Coder-32B-Instruct", 
                messages=messages,
                max_tokens=500
            )
            
            response = completion.choices[0].message.content
            print(response)
            return self.parse_json_response(response)
        except Exception as e:
            logging.error(f"Command parsing error: {e}")
            return None

    def parse_json_response(self, json_str):
        """
        Parse JSON response and update device states
        """
        try:
            import json
            parsed_data = json.loads(json_str)
            
            # Update device states
            for device, state in parsed_data.items():
                if device in self.device_states and device != 'chatbot message':
                    self.device_states[device] = state
            
            return parsed_data
        except json.JSONDecodeError:
            logging.error("Invalid JSON response")
            return None

    def send_device_states(self):
        """
        Send device states to microcontroller sequentially
        
        Args:
            device (str, optional): Specific device to update
            state (str, optional): State to set for the device
        """

        try:
            # Update specific device if provided
            # Ensure port is open
            if not self.ser.is_open:
                self.ser.open()
            print(self.device_states)
            # Send each device state sequentially
            for dev, dev_state in self.device_states.items():
                # Prepare CSV output for single device
                output = io.StringIO()
                csv_writer = csv.writer(output, delimiter=',')
                csv_writer.writerow([dev,dev_state])
                
                # Construct message with start and end markers
                message = f"START{output.getvalue().strip()}END\n"
                # print(message)
                # Send message
                self.ser.write(message.encode('utf-8'))
                # print("working till this part")
                print(f"Sent device state: {dev} = {dev_state}")
                
                # Small delay between device state updates
                time.sleep(0.3)

            return True
        
        except Exception as e:
            logging.error(f"Error sending device states: {e}")
            return False

    def wait_for_ack(self):
        """Wait for acknowledgment from the microcontroller"""
        try:
            start_time = time.time()
            while time.time() - start_time < 2:  # 2-second timeout
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
            # Parse command and update device states
            parsed_result = controller.parse_command(command)
            
            if parsed_result:
                # Send updated states to microcontroller
                controller.send_device_states()
                
                return jsonify({
                    'status': 'success', 
                    'message': parsed_result.get('chatbot message', 'Command processed'),
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
        # controller.send_device_states()
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
