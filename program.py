import socket
import re
import os
import time

class FTPClient:
    def __init__(self):
        self.control_socket = None
        self.connected = False

    #  connect/login
    def open(self, host, port=21):
        """Connect to FTP server and authenticate."""
        try:
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.settimeout(5.0)
            print(f"Connecting to {host}:{port}...")
            self.control_socket.connect((host, port))
            self.connected = True

            response = self._recv_response()
            print(response.strip())

            # get user/pass
            username = input("Username (or 'anonymous'): ")
            self._send_command(f"USER {username}")
            response = self._recv_response()
            print(response.strip())

            if response.startswith("331"):
                password = input("Password: ")
                self._send_command(f"PASS {password}")
                response = self._recv_response()
                print(response.strip())

            if response.startswith("230"):
                print(" Login successful!")
            elif response.startswith("530"):
                print(" Login failed: incorrect username or password.")
                self.connected = False
            else:
                print(" Unexpected login response:", response.strip())

        except Exception as e:
            print(f"Error connecting to server: {e}")
            self.connected = False

    # list dir
    def dir(self):
        """list files in the current directory."""
        if not self.connected:
            print("Not connected.")
            return

        ip, port = self._enter_passive_mode()
        if not ip:
            return

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as data_socket:
                data_socket.connect((ip, port))
                self._send_command("LIST")
                control_resp = self._recv_response()
                print(control_resp.strip())  

                # get dir list
                data = b""
                while True:
                    chunk = data_socket.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                print(data.decode('utf-8', errors='ignore'))

                print(self._recv_response().strip())  
        except Exception as e:
            print(f"Data connection error: {e}")

    # cd dir 
    def cd(self, path):
        """Change directory."""
        if not self.connected:
            print("Not connected.")
            return

        self._send_command(f"CWD {path}")
        response = self._recv_response()
        print(response.strip())
        code = self._parse_response_code(response)
        if code == 250:
            print(f"Changed directory to '{path}'")
        elif code == 550:
            print(f"Failed to change directory to '{path}'")
        else:
            print("Unexpected response:", response.strip())

    # download
    def get(self, filename):
        """Download a file from the FTP server."""
        if not self.connected:
            print("Not connected.")
            return

        ip, port = self._enter_passive_mode()
        if not ip:
            return

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as data_socket:
                
                data_socket.connect((ip, port))

                #request file
                self._send_command(f"RETR {filename}")
                control_resp = self._recv_response()
                print(control_resp.strip())

                code = self._parse_response_code(control_resp)
                if code != 150:
                    print(f"Server rejected RETR command (code {code}) — file may not exist or permission denied.")
                    return

                # write into file
                try:
                    with open(filename, "wb") as f:
                        while True:
                            chunk = data_socket.recv(4096)
                            if not chunk:
                                break
                            f.write(chunk)
                except Exception as e:
                    print(f"Error writing to file '{filename}': {e}")
                    if os.path.exists(filename):
                        os.remove(filename)
                    return

                final_resp = self._recv_response()
                print(final_resp.strip())
                if self._parse_response_code(final_resp) == 226:
                    print(f"File '{filename}' downloaded successfully.")
                else:
                    print(f"Unexpected final response: {final_resp.strip()}")

        except Exception as e:
            print(f"Download error: {e}")
            if os.path.exists(filename):
                os.remove(filename)

    # upload file
    def put(self, filename):
        """Upload a local file to the FTP server"""
        if not self.connected:
            print("Not connected.")
            return

        if not os.path.isfile(filename):
            print(f" File '{filename}' does not exist locally.")
            return

        ip, port = self._enter_passive_mode()
        if not ip:
            return

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as data_socket:
                data_socket.settimeout(10.0)
                data_socket.connect((ip, port))

                # file upload
                self._send_command(f"STOR {filename}")
                control_resp = self._recv_response()
                print(control_resp.strip())

                code = self._parse_response_code(control_resp)
                if code != 150:
                    print(f" Server rejected STOR command (code {code})")
                    return

                # send file data
                with open(filename, "rb") as f:
                    while True:
                        chunk = f.read(4096)
                        if not chunk:
                            break
                        data_socket.sendall(chunk)

                # delay
                time.sleep(0.5)
                data_socket.close()

                # final confirm
                final_resp = self._recv_response(timeout=10.0)
                print(final_resp.strip())

                if self._parse_response_code(final_resp) == 226:
                    print(f"File '{filename}' uploaded successfully.")
                else:
                    print(f"Unexpected final response: {final_resp.strip()}")

        except Exception as e:
            print(f"Upload error: {e}")

    # close connection
    def close(self):
        """close the current FTP session."""
        if self.connected:
            try:
                self._send_command("QUIT")
                print(self._recv_response().strip())
                self.control_socket.close()
            except Exception as e:
                print(f"Error closing connection: {e}")
            self.connected = False
            print("Connection closed.")
        else:
            print("No active connection.")

    #
    def _send_command(self, command):
        """Send a command over the control socket."""
        if self.connected and self.control_socket:
            self.control_socket.sendall((command + "\r\n").encode('utf-8'))
            

    def _recv_response(self, timeout=5.0):
        """handle multi-line response"""
        if not self.control_socket:
            return ""
        data = b""
        self.control_socket.settimeout(timeout)
        expected_code = None

        while True:
            try:
                chunk = self.control_socket.recv(4096)
                if not chunk:
                    break
                data += chunk
                text = data.decode('utf-8', errors='ignore')
                lines = text.splitlines()

                if not lines:
                    continue

                
                if expected_code is None and re.match(r'^(\d{3})-', lines[0]):
                    expected_code = lines[0][:3]

                
                pattern = rf'^{expected_code} ' if expected_code else r'^\d{3} '
                if re.search(pattern, lines[-1]):
                    break

            except socket.timeout:
                break

        return data.decode('utf-8', errors='ignore')



    def _enter_passive_mode(self):
        """Send PASV and parse IP/port for data connection"""
        self._send_command("PASV")
        response = self._recv_response()
        print(response.strip())

        match = re.search(r"\((\d+),(\d+),(\d+),(\d+),(\d+),(\d+)\)", response)
        if not match:
            print("Could not parse PASV response.")
            return None, None

        
        control_ip = self.control_socket.getpeername()[0]
        port = int(match.group(5)) * 256 + int(match.group(6))
        return control_ip, port

        
        

    def _parse_response_code(self, response):
        try:
            return int(response[:3])
        except:
            return 0

# main loop
def main():
    client = FTPClient()

    while True:
        command = input("ftp> ").strip()
        if not command:
            continue

        if command.startswith("open"):
            parts = command.split()
            if len(parts) >= 2:
                client.open(parts[1])
            else:
                print("Usage: open <hostname>")

        elif command == "dir":
            client.dir()

        elif command.startswith("cd"):
            parts = command.split(maxsplit=1)
            if len(parts) == 2:
                client.cd(parts[1])
            else:
                print("Usage: cd <directory>")

        elif command.startswith("get"):
            parts = command.split(maxsplit=1)
            if len(parts) == 2:
                client.get(parts[1])
            else:
                print("Usage: get <filename>")

        elif command.startswith("put"):
            parts = command.split(maxsplit=1)
            if len(parts) == 2:
                client.put(parts[1])
            else:
                print("Usage: put <filename>")

        elif command == "close":
            client.close()

        elif command == "quit":
            client.close()
            print("Goodbye!")
            break

        else:
            print("Unknown command. Try: open, dir, cd, get, put, close, quit")

if __name__ == "__main__":
    main()
