import time
import tkinter as tk
from pydub import AudioSegment
import numpy as np
import tempfile
import subprocess
import json
import os

# --- Configuration ---
MY_DATA = "my_data/"
SUBTITLES = "subtitles.json"

WORKING_DIR_NUMBER = 0
MARGIN = 0.5         # seconds of margin around each segment
START_EDITING = 0    # from which ID to start editing

class AudioEditorApp:
    def __init__(self, root, data, audio, audio_folder_name):
        self.root = root
        self.data = data
        self.audio = audio
        self.audio_folder_name = audio_folder_name
        self.total_duration = audio.duration_seconds

        # State management
        self.current_segment_index = self._find_start_index()
        self.last_time = -1
        
        # Initialize UI
        self._setup_widgets()
        
        # Load the first segment
        if self.current_segment_index < len(self.data["segments"]):
            self.load_segment(self.current_segment_index)
        else:
            print("No segments to edit.")
            self.root.destroy()

    def _find_start_index(self):
        """Find the list index corresponding to the START_EDITING ID."""
        for i, segment in enumerate(self.data["segments"]):
            if segment["id"] >= START_EDITING:
                return i
        return len(self.data["segments"]) # Start from the end if not found

    def _setup_widgets(self):
        """Create all GUI widgets once."""
        self.root.title("Audio Segment Editor")

        # Variables
        self.start_var = tk.DoubleVar()
        self.end_var = tk.DoubleVar()
        self.info_text = tk.StringVar()
        self.dragging = {'line': None}

        # --- Top Info Label ---
        tk.Label(self.root, textvariable=self.info_text, justify='left', font=("Arial", 10)).pack(pady=10, padx=10)

        # --- Canvas for Waveform ---
        self.canvas = tk.Canvas(self.root, height=140, bg='white')
        self.canvas.pack(fill='x', padx=10)
        self.canvas.bind('<Button-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_motion)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)

        # --- Time Labels Frame ---
        controls_frame = tk.Frame(self.root)
        controls_frame.pack(pady=5)
        tk.Label(controls_frame, text="Start (s):").grid(row=0, column=0)
        tk.Label(controls_frame, textvariable=self.start_var).grid(row=0, column=1, padx=5)
        tk.Label(controls_frame, text="End (s):").grid(row=0, column=2, padx=10)
        tk.Label(controls_frame, textvariable=self.end_var).grid(row=0, column=3, padx=5)
        
        # --- Buttons Frame ---
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)

        tk.Button(button_frame, text="Back", command=self.go_back).pack(side='left', padx=5)
        tk.Button(button_frame, text="Play Short", command=self.play_short).pack(side='left', padx=5)
        tk.Button(button_frame, text="Play Full", command=self.play_full).pack(side='left', padx=5)
        tk.Button(button_frame, text="Save and Next", command=self.save_and_next, font=("Arial", 10, "bold")).pack(side='left', padx=5)
        tk.Button(button_frame, text="+2s End", command=self.extend_end_by_2_sec).pack(side='left', padx=5)
        tk.Button(button_frame, text="Mark SKIPPED", fg="orange", command=self.mark_skipped).pack(side='left', padx=5)
        tk.Button(button_frame, text="SAVE & LEAVE", fg="red", command=self.leave).pack(side='right', padx=5)
        
        self.root.protocol("WM_DELETE_WINDOW", self.leave) # Handle window close button

    def load_segment(self, segment_index):
        """Loads a segment's data and updates the GUI."""
        if not (0 <= segment_index < len(self.data["segments"])):
            print("No more segments.")
            self.leave()
            return
            
        self.current_segment_index = segment_index
        item = self.data["segments"][self.current_segment_index]
        
        # Skip items that are marked as overlapping
        segment_start = max(item["start"], self.last_time)
        segment_end = item["end"]
        if segment_start >= segment_end:
            item["text"] = str(item["text"]).replace("SKIPPED-- ", "")
            item["text"] = "SKIPPED-- " + item["text"]
            self.save_and_next() # Automatically save as skipped and move on
            return

        self.start_var.set(round(segment_start, 3))
        self.end_var.set(round(segment_end, 3))

        # Update info text
        info = f'ID: {item["id"]} | User: {item["id_user"]}\n{item["text"]}'
        self.info_text.set(info)
        
        self.draw_waveform_and_markers()

    def draw_waveform_and_markers(self):
        """Clears and redraws the canvas with waveform and markers."""
        self.canvas.delete('all')
        
        current_item = self.data["segments"][self.current_segment_index]
        segment_start = self.start_var.get()
        segment_end = self.end_var.get()
        
        # Display window with margin
        self.disp_start = max(segment_start - MARGIN, 0)
        self.disp_end = min(segment_end + MARGIN, self.total_duration)
        duration = self.disp_end - self.disp_start
        
        canvas_width = self.canvas.winfo_width()
        if canvas_width <= 1: canvas_width = 1800 # Default width if not drawn yet
        canvas_height = 140
        self.canvas.config(width=canvas_width)

        # Draw waveform
        display_audio = self.audio[int(self.disp_start * 1000):int(self.disp_end * 1000)]
        samples = np.array(display_audio.get_array_of_samples())
        if display_audio.channels == 2:
            samples = samples.reshape((-1, 2)).mean(axis=1)

        if len(samples) == 0: return # Avoid errors on empty segments
        
        factor = max(1, len(samples) // canvas_width)
        num_samples = factor * canvas_width
        samples = samples[:num_samples].reshape((canvas_width, factor)).mean(axis=1)
        samples = samples / (np.max(np.abs(samples)) or 1)
        
        mid = canvas_height // 2
        for x, samp in enumerate(samples):
            y = int(samp * (mid - 10))
            self.canvas.create_line(x, mid - y, x, mid + y, fill='blue')

        # Draw tick marks
        for i in range(int(duration / 0.5) + 2):
            t = self.disp_start + i * 0.5
            if t > self.disp_end: break
            x = int(((t - self.disp_start) / duration) * canvas_width)
            self.canvas.create_line(x, 0, x, canvas_height, fill='gray', dash=(2, 2))
            self.canvas.create_text(x + 2, canvas_height - 10, text=f"{t:.1f}", anchor='nw', font=("Arial", 6))

        self._draw_markers()

    def _draw_markers(self):
        """Draws the start and end draggable lines."""
        self.canvas.delete('marker')
        canvas_width = self.canvas.winfo_width()
        duration = self.disp_end - self.disp_start
        if duration == 0: return

        # Start line
        start_t = self.start_var.get()
        start_x = int(((start_t - self.disp_start) / duration) * canvas_width)
        self.canvas.create_line(start_x, 0, start_x, 140, width=2, fill='green', tags=('marker', 'start_line'))
        self.canvas.create_text(start_x + 4, 4, text=f"{start_t:.2f}s", anchor='nw', fill='green', font=("Arial", 8, "bold"), tags='marker')

        # End line
        end_t = self.end_var.get()
        end_x = int(((end_t - self.disp_start) / duration) * canvas_width)
        self.canvas.create_line(end_x, 0, end_x, 140, width=2, fill='red', tags=('marker', 'end_line'))
        self.canvas.create_text(end_x + 4, 20, text=f"{end_t:.2f}s", anchor='nw', fill='red', font=("Arial", 8, "bold"), tags='marker')

    # --- Mouse Events ---
    def on_press(self, event):
        for tag in ('start_line', 'end_line'):
            coords = self.canvas.coords(tag)
            if coords and abs(event.x - coords[0]) < 10: # Increased tolerance
                self.dragging['line'] = tag
                break
    
    def on_motion(self, event):
        tag = self.dragging['line']
        if not tag: return
        
        canvas_width = self.canvas.winfo_width()
        duration = self.disp_end - self.disp_start
        if duration == 0: return

        x = max(0, min(event.x, canvas_width))
        t = self.disp_start + (x / canvas_width) * duration
        
        if tag == 'start_line':
            t = min(t, self.end_var.get() - 0.1)
            self.start_var.set(round(t, 3))
        else:
            t = max(t, self.start_var.get() + 0.1)
            self.end_var.set(round(t, 3))
        self._draw_markers()
    
    def on_release(self, event):
        self.dragging['line'] = None
        self.play_short() # Play the new boundary for confirmation

    # --- Button Commands ---
    def _play_segment(self, start_ms, end_ms):
        """Helper function to play an audio segment."""
        segment = self.audio[start_ms:end_ms]
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
            path = tmp.name
        try:
            segment.export(path, format='wav')
            subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path])
        finally:
            if os.path.exists(path):
                os.remove(path)

    def play_full(self):
        start_ms = int(self.start_var.get() * 1000)
        end_ms = int(self.end_var.get() * 1000)
        self._play_segment(start_ms, end_ms)

    def play_short(self):
        start_s = self.start_var.get()
        end_s = self.end_var.get()
        if end_s - start_s < 3:
            self.play_full()
            return
        
        # Play 1s at the start
        self._play_segment(int(start_s * 1000), int(start_s * 1000) + 1000)
        time.sleep(0.2)
        # Play 1s at the end
        self._play_segment(int(end_s * 1000) - 1000, int(end_s * 1000))
        
    def _save_current_segment(self):
        """Saves the current start/end times to the data object."""
        item = self.data["segments"][self.current_segment_index]
        item["start"] = self.start_var.get()
        item["end"] = self.end_var.get()
        self.last_time = item["end"]
        
    def save_and_next(self):
        self._save_current_segment()
        self.load_segment(self.current_segment_index + 1)

    def go_back(self):
        # We don't save when going back
        self.last_time = -1 # Reset last_time to allow re-editing previous clip's end
        self.load_segment(self.current_segment_index - 1)

    def extend_end_by_2_sec(self):
        """Extends the end time and reloads the view."""
        item = self.data["segments"][self.current_segment_index]
        item["end"] = round(min(item["end"] + 2.0, self.total_duration), 3)
        # Reload current segment with new end time
        self.load_segment(self.current_segment_index)

    def mark_skipped(self):
        item = self.data["segments"][self.current_segment_index]
        item["text"] = "SKIPPED-- " + item["text"].replace("SKIPPED-- ", "")
        self.info_text.set(f'ID: {item["id"]} | User: {item["id_user"]}\n{item["text"]}') # Update label immediately
        print(f"Segment {item['id']} marked as SKIPPED.")

    def leave(self):
        write_the_data_in_subtitle_json(self.audio_folder_name, self.data)
        print(f"Last edited ID: {self.data['segments'][self.current_segment_index]['id']}")
        self.root.destroy()

# --- JSON Handling ---
def get_the_data_in_subtitle_json(folder: str):
    with open(MY_DATA + folder + '/' + SUBTITLES, "r", encoding="utf-8") as file:
        data = json.load(file)
    return data

def write_the_data_in_subtitle_json(folder: str, data):
    with open(MY_DATA + folder + '/' + SUBTITLES, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

def get_working_folder_name(folder_id: int) -> str | None:
    for file in os.listdir(MY_DATA):
        if file.startswith(str(folder_id) + "."):
            return file
    return None


def main():
    name = get_working_folder_name(WORKING_DIR_NUMBER)
    if name is None:
        print(" <><><><><><><> Bad Working Folder Nr <><><><><><><>")
        exit(1)
    print("Working with: " + name)

    # Load audio
    audio_path = os.path.join(MY_DATA, name, ".".join(name.split(".")[1:]) + ".mp3")
    audio = AudioSegment.from_mp3(audio_path)

    # Setup and run the Tkinter app
    root = tk.Tk()
    data = get_the_data_in_subtitle_json(name)
    app = AudioEditorApp(root, data, audio, name)
    root.mainloop()

if __name__ == "__main__":
    main()