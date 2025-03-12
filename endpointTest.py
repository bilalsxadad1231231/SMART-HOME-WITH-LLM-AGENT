import requests

def test_voice_command_endpoint():
    # URL of the Flask endpoint
    url = 'http://127.0.0.1:5000/voice-command'
    
    # Loop to continuously take input from the user
    while True:
        # Get user input
        command = input("Enter your command (or type 'exit' to quit): ")
        
        # Exit the loop if the user types 'exit'
        if command.lower() == 'exit':
            print("Exiting...")
            break
        
        # Send the command to the Flask endpoint
        response = requests.post(url, data={'command': command})
        
        # Check if the request was successful
        if response.status_code == 200:
            # Print the response from the server
            print("Response from server:")
            print(response.json())
        else:
            print(f"Error: {response.status_code} - {response.text}")

if __name__ == "__main__":
    test_voice_command_endpoint()