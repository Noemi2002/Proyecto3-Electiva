import serial, time

s = serial.Serial('/dev/rfcomm0', 9600, timeout=5)
print("Conectando...")
time.sleep(3)

# Limpiar basura del handshake
s.reset_input_buffer()
s.reset_output_buffer()
time.sleep(0.5)

print("Enviando PING...")
s.write(b'PING\n')
s.flush()

# Leer respuestas por 3 segundos
print("Esperando respuesta...")
deadline = time.time() + 3
got_response = False

while time.time() < deadline:
    if s.in_waiting:
        line = s.readline().decode('utf-8', errors='ignore').strip()
        if line:
            print(f"Respuesta: {line}")
            got_response = True

if not got_response:
    print("Sin respuesta. Revisá la conexión.")

s.close()