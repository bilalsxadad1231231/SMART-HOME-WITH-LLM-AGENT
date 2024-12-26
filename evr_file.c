#include <avr/io.h>
#include <stdlib.h>
#include <string.h>
#include <util/delay.h>

#define F_CPU 16000000UL
#define BAUD_RATE 9600
#define MAX_CSV_LENGTH 256
#define MAX_DEVICES 8

// Precise Pin Definitions (Double-check with your actual hardware)
#define ROOM1_LIGHT_PIN PD7   // Pin 7
#define ROOM2_LIGHT_PIN PB2   // Pin 10
#define ROOM3_LIGHT_PIN PB5   // Pin 13 - IMPORTANT: DIRECT BIT
#define KITCHEN_LIGHT_PIN PD6 // Pin 6

#define ROOM1_FAN_PIN PB0     // Pin 8
#define ROOM2_FAN_PIN PB1     // Pin 9
#define ROOM3_FAN_PIN PB3     // Pin 11
#define KITCHEN_FAN_PIN PB4   // Pin 12

typedef struct {
    const char* name;
    volatile uint8_t* port;  // Pointer to PORT register
    uint8_t pin;             // Specific bit in the port
} DeviceState;

// CRITICAL: Use direct port and pin references
DeviceState deviceStates[] = {
    {"room 1 light", &PORTD, PD7},
    {"room 2 light", &PORTB, PB2},
    {"room 3 light", &PORTB, PB5},  // Direct bit reference
    {"kitchen light", &PORTD, PD6},
    {"room 1 fan", &PORTB, PB0},
    {"room 2 fan", &PORTB, PB1},
    {"room 3 fan", &PORTB, PB3},
    {"kitchen fan", &PORTB, PB4}
};

const uint8_t NUM_DEVICES = sizeof(deviceStates) / sizeof(deviceStates[0]);

void init_pins() {
    // Configure data direction registers
    DDRD |= (1 << PD7) | (1 << PD6);  // PORTD pins as output
    DDRB |= (1 << PB2) | (1 << PB5) |  // PORTB pins as output
            (1 << PB0) | (1 << PB1) | 
            (1 << PB3) | (1 << PB4);

    // Initial state - all devices off
    PORTD &= ~((1 << PD7) | (1 << PD6));
    PORTB &= ~((1 << PB2) | (1 << PB5) | 
               (1 << PB0) | (1 << PB1) | 
               (1 << PB3) | (1 << PB4));
}

void update_device_state(const char* device, const char* action) {
    for (uint8_t i = 0; i < NUM_DEVICES; i++) {
        if (strcmp(deviceStates[i].name, device) == 0) {
            // Determine state
            uint8_t new_state = (strcmp(action, "on") == 0) ? 1 : 0;

            // Direct port manipulation with pointer
            if (new_state) {
                *(deviceStates[i].port) |= (1 << deviceStates[i].pin);
                UART_transmit_string(action);  // Debug message
            } else {
                *(deviceStates[i].port) &= ~(1 << deviceStates[i].pin);
                UART_transmit_string(action);  // Debug message
            }
            break;
        }
    }
}

// Parse entire CSV state
void parse_csv_data(char* csv_string) {
    char* token;
    char device[32];
    char action[16];

    // First tokenize by newline to handle multiple devices
    token = strtok(csv_string, "\n");
    while (token != NULL) {
        // Reset device and action buffers
        memset(device, 0, sizeof(device));
        memset(action, 0, sizeof(action));

        // Split device name and action
        char* comma = strchr(token, ',');
        if (comma != NULL) {
            *comma = '\0';
            strncpy(device, token, sizeof(device) - 1);
            strncpy(action, comma + 1, sizeof(action) - 1);

            // Update device state
            update_device_state(device, action);
        }

        // Move to next line
        token = strtok(NULL, "\n");
    }
}

// UART Initialization (same as previous implementation)
void UART_init(unsigned int ubrr) {
    UBRR0H = (unsigned char)(ubrr>>8);
    UBRR0L = (unsigned char)ubrr;
    UCSR0B = (1<<RXEN0)|(1<<TXEN0);
    UCSR0C = (1<<USBS0)|(3<<UCSZ00);
}

// UART Receive Function
unsigned char UART_receive(void) {
    while (!(UCSR0A & (1<<RXC0)));
    return UDR0;
}

// UART Transmit Function for Strings
void UART_transmit_string(const char* str) {
    while (*str) {
        while (!(UCSR0A & (1<<UDRE0)));
        UDR0 = *str;
        str++;
    }
    while (!(UCSR0A & (1<<UDRE0)));
    UDR0 = '\r';
    while (!(UCSR0A & (1<<UDRE0)));
    UDR0 = '\n';
}

int main(void) {
    // Initialize pins
    init_pins();

    // Initialize UART
    UART_init(F_CPU/16/BAUD_RATE - 1);

    // Global variables for CSV parsing
    volatile char csv_buffer[MAX_CSV_LENGTH];
    volatile uint8_t buffer_index = 0;

    while (1) {
        char received_char = UART_receive();
        
        // Look for start of CSV
        if (received_char == 'S' && 
            UART_receive() == 'T' && 
            UART_receive() == 'A' && 
            UART_receive() == 'R' && 
            UART_receive() == 'T') {
            
            buffer_index = 0;
            
            // Receive CSV until END marker
            while (1) {
                received_char = UART_receive();
                
                // Check for END marker
                if (received_char == 'E' && 
                    UART_receive() == 'N' && 
                    UART_receive() == 'D') {
                    
                    // Null terminate the string
                    csv_buffer[buffer_index] = '\0';
                    
                    // Parse and process CSV
                    parse_csv_data((char*)csv_buffer);
                    
                    // Send acknowledgment
                    UART_transmit_string("CMD_OK");
                    
                    break;
                }
                
                // Store received character
                csv_buffer[buffer_index++] = received_char;
                
                // Prevent buffer overflow
                if (buffer_index >= MAX_CSV_LENGTH - 1) {
                    break;
                }
            }
        }
    }

    return 0;
}
