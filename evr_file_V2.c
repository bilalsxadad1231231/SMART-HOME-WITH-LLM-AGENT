#include <avr/io.h>
#include <stdlib.h>
#include <string.h>
#include <util/delay.h>
#include <Servo.h>

#define F_CPU 16000000UL
#define BAUD_RATE 9600
#define MAX_CSV_LENGTH 256
#define MAX_DEVICES 8

// Updated Pin Definitions
#define ROOM1_LIGHT_PIN PB0    // Pin 8
#define ROOM2_LIGHT_PIN PB1    // Pin 9
#define ROOM3_LIGHT_PIN PB2    // Pin 10
#define ROOM4_LIGHT_PIN PB3    // Pin 11
#define KITCHEN_LIGHT_PIN PB4  // Pin 12

#define DC_MOTOR_PIN PD4       // Pin 4
#define SERVO_MOTOR_PIN PD5    // Pin 5
#define REFRIGERATOR_PIN PD6   // Pin 6
#define TV_PIN PD7             // Pin 7

// Servo instance
Servo myservo;

typedef struct {
    const char* name;
    volatile uint8_t* port;
    uint8_t pin;
    uint8_t type;  // 0 for digital, 1 for servo, 2 for intensity control
} DeviceState;

// Updated device states array
DeviceState deviceStates[] = {
    {"room 1 light", &PORTB, PB0, 0},
    {"room 2 light", &PORTB, PB1, 2},  // With intensity control
    {"room 3 light", &PORTB, PB2, 2},  // With intensity control
    {"room 4 light", &PORTB, PB3, 0},
    {"kitchen light", &PORTB, PB4, 0},
    {"DC motor", &PORTD, PD4, 0},
    {"Servo motor", &PORTD, PD5, 1},   // Servo type
    {"Refrigerator", &PORTD, PD6, 0},
    {"TV", &PORTD, PD7, 0}
};

const uint8_t NUM_DEVICES = sizeof(deviceStates) / sizeof(deviceStates[0]);

void init_pins() {
    // Configure PORTB pins (8-12) as outputs for lights
    DDRB |= (1 << PB0) | (1 << PB1) | (1 << PB2) | (1 << PB3) | (1 << PB4);
    
    // Configure PORTD pins (4-7) as outputs for other devices
    DDRD |= (1 << PD4) | (1 << PD5) | (1 << PD6) | (1 << PD7);
    
    // Initialize all outputs to LOW
    PORTB &= ~((1 << PB0) | (1 << PB1) | (1 << PB2) | (1 << PB3) | (1 << PB4));
    PORTD &= ~((1 << PD4) | (1 << PD5) | (1 << PD6) | (1 << PD7));
    
    // Initialize servo
    myservo.attach(SERVO_MOTOR_PIN);
    myservo.write(90);  // Center position
}

void update_device_state(const char* device, const char* action, const char* value) {
    for (uint8_t i = 0; i < NUM_DEVICES; i++) {
        if (strcmp(deviceStates[i].name, device) == 0) {
            switch (deviceStates[i].type) {
                case 0:  // Digital ON/OFF
                    if (strcmp(action, "on") == 0) {
                        *(deviceStates[i].port) |= (1 << deviceStates[i].pin);
                    } else {
                        *(deviceStates[i].port) &= ~(1 << deviceStates[i].pin);
                    }
                    break;
                    
                case 1:  // Servo motor
                    if (strcmp(action, "clock") == 0) {
                        int angle = atoi(value);
                        myservo.write(angle);
                    } else if (strcmp(action, "anti") == 0) {
                        int angle = atoi(value);
                        myservo.write(180 - angle);
                    }
                    break;
                    
                case 2:  // Intensity control (PWM)
                    if (strcmp(action, "on") == 0) {
                        int intensity = atoi(value);
                        // Map intensity (0-100) to PWM (0-255)
                        int pwm_value = (intensity * 255) / 100;
                        if (deviceStates[i].pin == PB1) {
                            OCR1A = pwm_value;
                        } else if (deviceStates[i].pin == PB2) {
                            OCR1B = pwm_value;
                        }
                    } else {
                        if (deviceStates[i].pin == PB1) {
                            OCR1A = 0;
                        } else if (deviceStates[i].pin == PB2) {
                            OCR1B = 0;
                        }
                    }
                    break;
            }
            // Send acknowledgment
            UART_transmit_string("OK");
            return;
        }
    }
}

void init_pwm() {
    // Configure Timer1 for PWM operation
    TCCR1A |= (1 << COM1A1) | (1 << COM1B1) | (1 << WGM10);
    TCCR1B |= (1 << CS11);  // Prescaler = 8
    
    // Set initial PWM values to 0
    OCR1A = 0;
    OCR1B = 0;
}

void parse_csv_data(char* csv_string) {
    char* token;
    char device[32];
    char action[16];
    char value[16];

    token = strtok(csv_string, "\n");
    while (token != NULL) {
        memset(device, 0, sizeof(device));
        memset(action, 0, sizeof(action));
        memset(value, 0, sizeof(value));

        // Split CSV into device,action,value
        char* first_comma = strchr(token, ',');
        if (first_comma != NULL) {
            *first_comma = '\0';
            strncpy(device, token, sizeof(device) - 1);
            
            char* second_comma = strchr(first_comma + 1, ',');
            if (second_comma != NULL) {
                *second_comma = '\0';
                strncpy(action, first_comma + 1, sizeof(action) - 1);
                strncpy(value, second_comma + 1, sizeof(value) - 1);
            } else {
                strncpy(action, first_comma + 1, sizeof(action) - 1);
            }

            update_device_state(device, action, value);
        }

        token = strtok(NULL, "\n");
    }
}

// UART functions remain the same as in your original code
void UART_init(unsigned int ubrr) {
    UBRR0H = (unsigned char)(ubrr>>8);
    UBRR0L = (unsigned char)ubrr;
    UCSR0B = (1<<RXEN0)|(1<<TXEN0);
    UCSR0C = (1<<USBS0)|(3<<UCSZ00);
}

unsigned char UART_receive(void) {
    while (!(UCSR0A & (1<<RXC0)));
    return UDR0;
}

void UART_transmit_string(const char* str) {
    while (*str) {
        while (!(UCSR0A & (1<<UDRE0)));
        UDR0 = *str++;
    }
    while (!(UCSR0A & (1<<UDRE0)));
    UDR0 = '\r';
    while (!(UCSR0A & (1<<UDRE0)));
    UDR0 = '\n';
}

int main(void) {
    // Initialize all subsystems
    init_pins();
    init_pwm();
    UART_init(F_CPU/16/BAUD_RATE - 1);

    volatile char csv_buffer[MAX_CSV_LENGTH];
    volatile uint8_t buffer_index = 0;

    while (1) {
        char received_char = UART_receive();
        
        if (received_char == 'S' && 
            UART_receive() == 'T' && 
            UART_receive() == 'A' && 
            UART_receive() == 'R' && 
            UART_receive() == 'T') {
            
            buffer_index = 0;
            
            while (1) {
                received_char = UART_receive();
                
                if (received_char == 'E' && 
                    UART_receive() == 'N' && 
                    UART_receive() == 'D') {
                    
                    csv_buffer[buffer_index] = '\0';
                    parse_csv_data((char*)csv_buffer);
                    UART_transmit_string("CMD_OK");
                    break;
                }
                
                csv_buffer[buffer_index++] = received_char;
                
                if (buffer_index >= MAX_CSV_LENGTH - 1) {
                    break;
                }
            }
        }
    }

    return 0;
}