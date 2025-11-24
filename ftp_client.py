import socket
import re
import os
import time


class FTPClient:
    def __init__(self, is_gui=False):
        self.control_socket = None
        self.connected = False
        self.is_gui = is_gui        
        self.output_callback = print  

    def set_output_callback(self, callback):
        
        if callback is None:
            self.output_callback = print
        else:
            self.output_callback = callback

    def _log(self, message: str):
        """Helper to send messages to the configured output callback."""
        try:
            self.output_callback(message)
        except Exception:
            # Fallback 
            print(message)

    #  connect/login 
    def open(self, host, port=21):
        # Connect to FTP server and authenticate
        try:
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.settimeout(5.0)
            self._log(f"Connecting to {host}:{port}...")
            self.control_socket.connect((host, port))
            self.connected = True

            response = self._recv_response()
            self._log(response.strip())

            # If running under GUI, we stop here.
            if self.is_gui:
                return

            # CLI login flow 
            username = input("Username (or 'anonymous'): ")
            password = input("Password: ")

            self.login(username, password)

        except Exception as e:
            self._log(f"Error connecting to server: {e}")
            self.connected = False

    def login(self, username, password=None):
        """
        Perform the USER/PASS sequence. Used by both CLI and GUI.
        """
        if not self.connected or not self.control_socket:
            self._log("Not connected.")
            return False

        try:
            if not username:
                username = "anonymous"

            # Send USER
            self._send_command(f"USER {username}")
            response = self._recv_response()
            self._log(response.strip())

            # If the server requests a password, send PASS (if provided)
            if response.startswith("331") and password is not None:
                self._send_command(f"PASS {password}")
                response = self._recv_response()
                self._log(response.strip())

            # Evaluate final login response
            if response.startswith("230"):
                self._log(" Login successful!")
                return True
            elif response.startswith("530"):
                self._log(" Login failed: incorrect username or password.")
                self.connected = False
                return False
            else:
                self._log(" Unexpected login response: " + response.strip())
                return False

        except Exception as e:
            self._log(f"Error during login: {e}")
            self.connected = False
            return False

    # list dir 
    def dir(self):
        if not self.connected:
            self._log("Not connected.")
            return

        lines = self.list_directory()
        if lines:
            self._log("\n".join(lines))

    def list_directory(self):
        """
        Perform a LIST in passive mode and return the directory listing
        as a list of lines. This is used both by the CLI (via dir())
        and by the GUI (to populate the remote file list).
        """
        if not self.connected:
            self._log("Not connected.")
            return []

        ip, port = self._enter_passive_mode()
        if not ip:
            return []

        listing_lines = []

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as data_socket:
                data_socket.connect((ip, port))
                self._send_command("LIST")
                control_resp = self._recv_response()
                self._log(control_resp.strip())

                # get dir list
                data = b""
                while True:
                    chunk = data_socket.recv(4096)
                    if not chunk:
                        break
                    data += chunk

                listing_text = data.decode('utf-8', errors='ignore')
                listing_lines = listing_text.splitlines()

                final_resp = self._recv_response()
                self._log(final_resp.strip())

        except Exception as e:
            self._log(f"Data connection error: {e}")
            return []

        return listing_lines

    # cd dir
    def cd(self, path):
        if not self.connected:
            self._log("Not connected.")
            return

        self._send_command(f"CWD {path}")
        response = self._recv_response()
        self._log(response.strip())
        code = self._parse_response_code(response)
        if code == 250:
            self._log(f"Changed directory to '{path}'")
        elif code == 550:
            self._log(f"Failed to change directory to '{path}'")
        else:
            self._log("Unexpected response: " + response.strip())

    # download
    def get(self, filename):
        if not self.connected:
            self._log("Not connected.")
            return

        ip, port = self._enter_passive_mode()
        if not ip:
            return

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as data_socket:
                data_socket.connect((ip, port))

                # request file
                self._send_command(f"RETR {filename}")
                control_resp = self._recv_response()
                self._log(control_resp.strip())

                code = self._parse_response_code(control_resp)
                if code != 150:
                    self._log(
                        f"Server rejected RETR command (code {code}) — file may not exist or permission denied."
                    )
                    return

                # write into file (local name is same as remote here)
                try:
                    with open(filename, "wb") as f:
                        while True:
                            chunk = data_socket.recv(4096)
                            if not chunk:
                                break
                            f.write(chunk)
                except Exception as e:
                    self._log(f"Error writing to file '{filename}': {e}")
                    if os.path.exists(filename):
                        os.remove(filename)
                    return

                final_resp = self._recv_response()
                self._log(final_resp.strip())
                if self._parse_response_code(final_resp) == 226:
                    self._log(f"File '{filename}' downloaded successfully.")
                else:
                    self._log(f"Unexpected final response: {final_resp.strip()}")

        except Exception as e:
            self._log(f"Download error: {e}")
            if os.path.exists(filename):
                os.remove(filename)

    # upload file
    def put(self, filename):
        if not self.connected:
            self._log("Not connected.")
            return

        local_path = filename
        if not os.path.isfile(local_path):
            self._log(f" File '{local_path}' does not exist locally.")
            return

        ip, port = self._enter_passive_mode()
        if not ip:
            return

        remote_name = os.path.basename(local_path)

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as data_socket:
                data_socket.settimeout(10.0)
                data_socket.connect((ip, port))

                # file upload
                self._send_command(f"STOR {remote_name}")
                control_resp = self._recv_response()
                self._log(control_resp.strip())

                code = self._parse_response_code(control_resp)
                if code != 150:
                    self._log(f" Server rejected STOR command (code {code})")
                    return

                # send file data
                with open(local_path, "rb") as f:
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
                self._log(final_resp.strip())

                if self._parse_response_code(final_resp) == 226:
                    self._log(f"File '{remote_name}' uploaded successfully.")
                else:
                    self._log(f"Unexpected final response: {final_resp.strip()}")

        except Exception as e:
            self._log(f"Upload error: {e}")

    # close connection
    def close(self):
        if self.connected:
            try:
                self._send_command("QUIT")
                resp = self._recv_response().strip()
                if resp:
                    self._log(resp)
                self.control_socket.close()
            except Exception as e:
                self._log(f"Error closing connection: {e}")
            self.connected = False
            self._log("Connection closed.")
        else:
            self._log("No active connection.")

    # send command
    def _send_command(self, command):
        if self.connected and self.control_socket:
            try:
                self.control_socket.sendall((command + "\r\n").encode('utf-8'))
            except Exception as e:
                self._log(f"Error sending command '{command}': {e}")

    def _recv_response(self, timeout=5.0):
        # handle multi-line response
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

                # detect multi-line code
                if expected_code is None and re.match(r'^(\d{3})-', lines[0]):
                    expected_code = lines[0][:3]

                pattern = rf'^{expected_code} ' if expected_code else r'^\d{3} '
                if re.search(pattern, lines[-1]):
                    break

            except socket.timeout:
                break

        return data.decode('utf-8', errors='ignore')

    # enter passive mode
    def _enter_passive_mode(self):
        self._send_command("PASV")
        response = self._recv_response()
        self._log(response.strip())

        match = re.search(r"\((\d+),(\d+),(\d+),(\d+),(\d+),(\d+)\)", response)
        if not match:
            self._log("Could not parse PASV response.")
            return None, None

        control_ip = self.control_socket.getpeername()[0]
        port = int(match.group(5)) * 256 + int(match.group(6))
        return control_ip, port

    def _parse_response_code(self, response):
        try:
            return int(response[:3])
        except Exception:
            return 0


# main loop 
def main():
    client = FTPClient(is_gui=False)  

    while True:
        try:
            command = input("ftp> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            client.close()
            print("Goodbye!")
            break

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
