import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from ftp_client import FTPClient


class LoginDialog(simpledialog.Dialog):
    """username and password."""

    def body(self, master):
        tk.Label(master, text="Username:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        tk.Label(master, text="Password:").grid(row=1, column=0, sticky="e", padx=5, pady=5)

        self.username_entry = tk.Entry(master)
        self.password_entry = tk.Entry(master, show="*")

        self.username_entry.grid(row=0, column=1, padx=5, pady=5)
        self.password_entry.grid(row=1, column=1, padx=5, pady=5)

        return self.username_entry  

    def apply(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        self.result = (username, password)


class FTPClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FTP Client GUI")

        # FTP client in GUI mode
        self.client = FTPClient(is_gui=True)
        self.client.set_output_callback(self.append_log)

        # Track local directory
        self.local_path = os.getcwd()
        self.remote_entries = []  # list of dicts
        self.local_entries = []   # list of filenames

        self._build_widgets()
        self.refresh_local_files()

    def _build_widgets(self):
        #  Top connection bar 
        top_frame = ttk.Frame(self.root)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        ttk.Label(top_frame, text="Host:").pack(side=tk.LEFT)
        self.host_entry = ttk.Entry(top_frame, width=30)
        self.host_entry.pack(side=tk.LEFT, padx=5)
        self.host_entry.insert(0, "ftp.gnu.org")  # you can change

        self.connect_button = ttk.Button(top_frame, text="Connect", command=self.on_connect)
        self.connect_button.pack(side=tk.LEFT, padx=5)

        self.disconnect_button = ttk.Button(top_frame, text="Disconnect", command=self.on_disconnect)
        self.disconnect_button.pack(side=tk.LEFT, padx=5)

        self.quit_button = ttk.Button(top_frame, text="Quit", command=self.on_quit)
        self.quit_button.pack(side=tk.RIGHT, padx=5)

        # Main three-column area 
        main_frame = ttk.Frame(self.root)
        main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Column 1: Server responses (scrollable text)
        resp_frame = ttk.Frame(main_frame)
        resp_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        ttk.Label(resp_frame, text="Server Responses").pack(anchor="w")
        self.response_text = tk.Text(resp_frame, wrap="word", height=20)
        resp_scroll = ttk.Scrollbar(resp_frame, orient=tk.VERTICAL, command=self.response_text.yview)
        self.response_text.configure(yscrollcommand=resp_scroll.set)

        self.response_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        resp_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Column 2: Remote files (scrollable listbox)
        remote_frame = ttk.Frame(main_frame)
        remote_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        ttk.Label(remote_frame, text="Remote Files").pack(anchor="w")
        self.remote_listbox = tk.Listbox(remote_frame, activestyle="dotbox")
        remote_scroll = ttk.Scrollbar(remote_frame, orient=tk.VERTICAL, command=self.remote_listbox.yview)
        self.remote_listbox.configure(yscrollcommand=remote_scroll.set)

        self.remote_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        remote_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Double-click on remote file/dir
        self.remote_listbox.bind("<Double-Button-1>", self.on_remote_double_click)

        # Column 3: Local files (scrollable listbox)
        local_frame = ttk.Frame(main_frame)
        local_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(local_frame, text="Local Files").pack(anchor="w")
        self.local_listbox = tk.Listbox(local_frame, activestyle="dotbox")
        local_scroll = ttk.Scrollbar(local_frame, orient=tk.VERTICAL, command=self.local_listbox.yview)
        self.local_listbox.configure(yscrollcommand=local_scroll.set)

        self.local_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        local_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Double-click on local file to upload
        self.local_listbox.bind("<Double-Button-1>", self.on_local_double_click)

    #  Logging 
    def append_log(self, message: str):
        """Append a line to the server responses text area."""
        if not message:
            return
        self.response_text.insert(tk.END, message + "\n")
        self.response_text.see(tk.END)

    # Button handlers 
    def on_connect(self):
        host = self.host_entry.get().strip()
        if not host:
            messagebox.showwarning("Host Required", "Please enter a remote host name.")
            return

        # If already connected, close first
        if self.client.connected:
            self.client.close()

        self.append_log(f"Attempting to connect to {host}...")
        self.client.open(host)

        if not self.client.connected:
            messagebox.showerror("Connection Failed", "Could not connect to the FTP server.")
            return

        # Show login dialog 
        dialog = LoginDialog(self.root, title="FTP Login")
        if not dialog.result:
            # User closed/canceled the dialog
            self.append_log("Login canceled by user.")
            return

        username, password = dialog.result
        success = self.client.login(username, password)

        if success:
            self.refresh_remote_files()
        else:
            messagebox.showerror("Login Failed", "Login was not successful.")

    def on_disconnect(self):
        self.client.close()
        self.remote_listbox.delete(0, tk.END)
        self.remote_entries.clear()

    def on_quit(self):
        if self.client.connected:
            self.client.close()
        self.root.destroy()

    #  Remote / local list handling
    def refresh_remote_files(self):
        if not self.client.connected:
            return

        lines = self.client.list_directory()
        self.remote_entries = []
        self.remote_listbox.delete(0, tk.END)

        for line in lines:
            line = line.strip()
            if not line:
                continue

            name = self._extract_name_from_list_line(line)
            if not name:
                continue

            # detect directory 
            is_dir = line.startswith("d") or "<DIR>" in line

            display = f"[DIR] {name}" if is_dir else name
            self.remote_entries.append({"name": name, "is_dir": is_dir})
            self.remote_listbox.insert(tk.END, display)

    def refresh_local_files(self):
        """Populate the local file list from the current working directory."""
        self.local_listbox.delete(0, tk.END)
        self.local_entries = []

        try:
            entries = sorted(os.listdir(self.local_path))
        except Exception as e:
            self.append_log(f"Error listing local directory '{self.local_path}': {e}")
            return

        for name in entries:
            full_path = os.path.join(self.local_path, name)
            if os.path.isdir(full_path):
                display = f"[DIR] {name}"
            else:
                display = name
            self.local_entries.append(name)
            self.local_listbox.insert(tk.END, display)

    @staticmethod
    def _extract_name_from_list_line(line: str) -> str:
        """
         to extract the filename from an FTP LIST line.
        """
        parts = line.split()
        if len(parts) < 1:
            return ""
        # fallback: take the last element as the name
        return parts[-1]

    #  Mouse handlers 
    def on_remote_double_click(self, event):
        """Handle double-click on a remote entry."""
        if not self.remote_entries:
            return

        selection = self.remote_listbox.curselection()
        if not selection:
            return

        index = selection[0]
        entry = self.remote_entries[index]
        name = entry["name"]
        is_dir = entry["is_dir"]

        if is_dir:
            # Change directory on the server
            self.client.cd(name)
            self.refresh_remote_files()
        else:
            # Download file
            self.client.get(name)
            self.refresh_local_files()

    def on_local_double_click(self, event):
        """Handle double-click on a local entry."""
        if not self.local_entries:
            return

        selection = self.local_listbox.curselection()
        if not selection:
            return

        index = selection[0]
        name = self.local_entries[index]
        full_path = os.path.join(self.local_path, name)

        if os.path.isdir(full_path):
            messagebox.showinfo("Upload", "Uploading directories is not supported.")
            return

        if not self.client.connected:
            messagebox.showwarning("Not Connected", "Connect and log in before uploading.")
            return

        self.client.put(full_path)
        # After upload, you can refresh remote list so the file appears
        self.refresh_remote_files()


def main():
    root = tk.Tk()
    app = FTPClientGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
