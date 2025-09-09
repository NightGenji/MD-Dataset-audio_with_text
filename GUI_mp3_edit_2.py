import sys
from threading import Thread
import time
import tkinter as tk
from tkinter import messagebox
from pydub import AudioSegment
import numpy as np
import tempfile
import subprocess
import json
import os
# TODO - recommended to check the code beforehand, it is not tested(too much)
MY_DATA = "my_data/"
SUBTITLES = "subtitles.json"

SEGMENTS  = "segments"
ID_SEG    = "id"
START_SEG = "start"
END_SEG   = "end"
TEXT_SEG  = "text"
ID_USER   = "id_user"
LIST_TIME = "list_time"

SKIPPED = "SKIPPED-- "

WORKING_DIR_NUMBER = 5
MARGIN = 1.5            # seconds of margin around each segment
LENGTH_PER_05_SEC = 50  # how many pixels per 0.5 seconds
START_EDITING = 0    # from wich ID to start editing

"""this script takes a WORKING_DIR_NUMBER value as first argument if any"""
"""then it takes a START_EDITING value as a second argument if any"""

def get_the_data_in_subtitle_json(folder: str):
    with open(MY_DATA + folder + '/' + SUBTITLES, "r", encoding="utf-8") as file:
        data = json.load(file)
    return data

def write_the_data_in_subtitle_json(folder: str, data):
    with open(MY_DATA + folder + '/' + SUBTITLES, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

def get_working_folder_name(folder_id: int) -> str:
    name = None
    for file in os.listdir(MY_DATA):
        if file.startswith(str(folder_id) + "."):
            name = file
            break
    if name is None:
        print("<><><> Bad Working Folder Nr <><><>")
        exit(1)
    print("Working with: " + name)
    return name

class Repair_Audio:
    def __init__(self, root: tk.Tk, data, audio: AudioSegment, folder, start_id):
        self.root = root
        self.data = data
        self.audio = audio
        self.folder = folder

        # Position Tracking
        self.id_curr_seg = start_id
        self.last_saved_id = -1
        self.last_end_time = -1  # the end time of the previous edited seg

        # Info/Variables
        self.start_var = tk.DoubleVar()
        self.end_var = tk.DoubleVar()
        self.info_text = tk.StringVar()
        self.txt: tk.Text  # used to modify TEXT for segments

        # The time margins of the audio drawing
        self.disp_start: float
        self.disp_end: float

        # Markers
        self.markers: list[tk.DoubleVar]
        self.select_mark = tk.IntVar()  # index of last selected marker
        self.dragging = {'line': None}

        # Play threads
        self.play_thread: Thread = None

        self.upload_widgets()
        self.load_segment()

    # --- Main functions ---
    def upload_widgets(self):
        self.root.title("Editing Segment Time")
        self.root.protocol("WM_DELETE_WINDOW", self.leave) # Calls leave() when i press X
        tk.Label(self.root, textvariable=self.info_text, justify='left').pack(pady=5)

        self.canvas = tk.Canvas(self.root, height=140, bg='white')
        self.canvas.pack()
        self.canvas.bind('<Button-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_motion)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)

        frame = tk.Frame(self.root)
        frame.pack(pady=5)
        tk.Label(frame, text="Start (s):")            .grid(row=0, column=0)
        tk.Label(frame, textvariable=self.start_var)  .grid(row=0, column=1, padx=5)
        tk.Label(frame, text="End (s):")              .grid(row=0, column=2, padx=10)
        tk.Label(frame, textvariable=self.end_var)    .grid(row=0, column=3, padx=5)
        tk.Label(frame, text="Idx_Mrk:")              .grid(row=0, column=4, padx=10)
        tk.Label(frame, textvariable=self.select_mark).grid(row=0, column=5, padx=5)

        frame_butt_up = tk.Frame(self.root)
        frame_butt_up.pack(side="top")
        frame_sec_row = tk.Frame(self.root)
        frame_sec_row.pack(side="top")
        frame_butt_down = tk.Frame(self.root)
        frame_butt_down.pack(side="bottom")

        tk.Button(frame_butt_up, text="-0.04",   command=lambda: self.move_marker(-0.04)).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="-0.01",   command=lambda: self.move_marker(-0.01)).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="-0.005",  command=lambda: self.move_marker(-0.005)).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="Play",    command=self.play).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text=" ■ ",     command=self.stop_playing).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="+0.005",  command=lambda: self.move_marker(0.005)).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="+0.01",   command=lambda: self.move_marker(0.01)).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="+0.04",   command=lambda: self.move_marker(0.04)).pack(pady=2, side='left')

        tk.Button(frame_sec_row, text="Play_last 1",   command=lambda: self.play_last(0)).pack(pady=2, side='left')
        tk.Button(frame_sec_row, text="Play SHORT",    command=self.play_short).pack(pady=2, side='left')
        tk.Button(frame_sec_row, text="Play_last 1.1", command=lambda: self.play_last(0.1)).pack(pady=2, side='left')

        tk.Button(self.root, text="Save and Next", command=self.save_and_next, fg="green").pack(pady=2)
        tk.Button(self.root, text="+2 sec",        command=self.extend_end_by_2_sec).pack(pady=2)

        tk.Button(frame_butt_down, text="Leave Editing Mode", command=self.leave, fg="red").pack(pady=2, side='right')
        tk.Button(frame_butt_down, text="Mark SKIPPED",       command=self.mark_skipped, fg="red").pack(pady=2, side='right')
        tk.Button(frame_butt_down, text="Back",               command=self.back).pack(pady=2, side='left')

        text_frame = tk.Frame(self.root)
        text_frame.pack(side="bottom")
        self.txt = tk.Text(text_frame, height=8, width=80, wrap="word")
        self.txt.pack()
        self.txt.insert(tk.END, self.data[SEGMENTS][self.id_curr_seg][TEXT_SEG])

        tk.Button(text_frame, text="Save Text", command=self.save_edited_text, fg="green").pack(padx=5)

    def load_segment(self):
        """This function dictates wich segments to edit, can be modified to suit the user's needs"""
        while True:
            if not (0 <= self.id_curr_seg < len(self.data[SEGMENTS])):
                self.leave()
            item = self.data[SEGMENTS][self.id_curr_seg]
            if str(item[TEXT_SEG]).startswith(SKIPPED):
                self.id_curr_seg += 1
                continue
            if self.last_end_time >= item[END_SEG]:
                item[TEXT_SEG] = SKIPPED + item[TEXT_SEG]
                self.id_curr_seg += 1
                continue
            break

        # Variables
        self.start_var.set(item[START_SEG] if self.last_end_time == -1 else self.last_end_time)
        self.end_var.set(item[END_SEG])
        self.info_text.set(f'ID: {item[ID_SEG]} | User: {item[ID_USER]}')
        self.select_mark.set(-1)

        self.disp_start = max(self.start_var.get() - MARGIN, 0)
        self.disp_end = min(self.end_var.get() + MARGIN, self.audio.duration_seconds)

        # Change canvas size
        width = min(1900, int(((self.disp_end - self.disp_start) / 0.5) * LENGTH_PER_05_SEC))
        self.canvas.config(width=width)

        # Update Text
        self.txt.delete("1.0", tk.END)
        self.txt.insert(tk.END, item[TEXT_SEG])

        self.define_markers()
        self.draw_all()

    def define_markers(self):
        self.markers = [self.start_var, self.end_var]

    def draw_markers(self):
        self.canvas.delete('marker')
        self.canvas.delete('selection')
        self.canvas.delete('marker_text')

        canv_height, canv_width = self.canvas.winfo_height(), self.canvas.winfo_width()
        duration = self.disp_end - self.disp_start

        x_s = int(((self.start_var.get() - self.disp_start) / duration) * canv_width)
        x_e = int(((self.end_var.get()   - self.disp_start) / duration) * canv_width)

        try:
            self.canvas.create_rectangle(x_s, 0, x_e, canv_height, fill='skyblue', stipple='gray25',
                                         width=0, tags='selection')
        except Exception:
            self.canvas.create_rectangle(x_s, 0, x_e, canv_height, fill='skyblue',
                                         width=0, tags='selection')

        for idx, tk_sec in enumerate(self.markers):
            x = int(((tk_sec.get() - self.disp_start) / duration) * canv_width)
            self.canvas.create_line(x, 0, x, canv_height, width=2, tags=('marker', f'marker_{idx}'))
            self.canvas.create_text(x + 4, 4, text=f"{tk_sec.get():.3f}s", anchor='nw', tags='marker_text')
        
        self.canvas.itemconfig('marker', fill='#006400')
        if self.select_mark.get() != -1:
            self.canvas.itemconfig(f'marker_{self.select_mark.get()}', fill='red')

    def draw_all(self):
        self.canvas.update_idletasks()
        self.canvas.delete('drawing')

        duration = self.disp_end - self.disp_start
        canvas_width, canvas_height = self.canvas.winfo_width(), self.canvas.winfo_height()

        # Waveform
        display_audio = self.audio[int(self.disp_start * 1000):int(self.disp_end * 1000)]
        samples = np.array(display_audio.get_array_of_samples())

        if display_audio.channels > 1:
            samples = samples.reshape((-1, display_audio.channels)).mean(axis=1)

        # didn't understand pretty much nothing here... for the next time
        factor = max(1, len(samples) // canvas_width)
        samples = samples[:factor * canvas_width].reshape((canvas_width, factor)).mean(axis=1)
        samples = samples / np.max(np.abs(samples))

        mid = canvas_height // 2
        for x, samp in enumerate(samples):
            y = int(samp * (mid - 10))
            self.canvas.create_line(x, mid - y, x, mid + y, tags='drawing')

        # Tick marks every 0.5s
        for i in range(int(duration / 0.5) + 1):
            t = self.disp_start + i * 0.5
            x = int(((t - self.disp_start) / duration) * canvas_width)
            self.canvas.create_line(x, 0, x, canvas_height, fill='gray', dash=(2, 2), tags='drawing')
            self.canvas.create_text(x + 2, canvas_height - 10, text=f"{t:.3f}", anchor='nw', tags='drawing')
        
        self.draw_markers()

    # --- Mouse Events ---
    def on_press(self, event: tk.Event):
        for idx, _ in enumerate(self.markers):
            coords = self.canvas.coords(f'marker_{idx}')
            if coords and abs(event.x - coords[0]) < 15:
                self.dragging['line'] = f'marker_{idx}'

                if self.select_mark.get() != -1:
                    self.canvas.itemconfig(f'marker_{self.select_mark.get()}', fill='#006400')
                self.select_mark.set(idx)
                self.canvas.itemconfig(f'marker_{idx}', fill='red')

                break

    def on_motion(self, event: tk.Event):
        if not (0 <= event.x <= self.canvas.winfo_width()):
            return
        tag: str = self.dragging['line']
        if not tag: return

        duration = self.disp_end - self.disp_start
        t = self.disp_start + (event.x / self.canvas.winfo_width()) * duration
        idx = int(tag.replace('marker_', ''))
        obj = self.markers[idx]

        if idx == 0:
            up_obj = self.markers[idx + 1]
            if t < self.disp_start or t >= up_obj.get():
                return
        elif idx == len(self.markers) - 1:
            down_obj = self.markers[idx - 1]
            if t > self.disp_end or down_obj.get() >= t:
                return
        else:
            down_obj = self.markers[idx - 1]
            up_obj = self.markers[idx + 1]
            if t >= up_obj.get() or down_obj.get() >= t:
                return

        obj.set(round(t, 3))
        self.draw_markers()

    def on_release(self, event: tk.Event):
        self.dragging['line'] = None
        self.canvas.itemconfig(f'marker_{self.select_mark.get()}', fill='red')

    # --- Button functions ---
    def _play_seg(self, start_ms, end_ms, end_flag: bool):
        segment = self.audio[start_ms : end_ms]
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
            path = tmp.name
        segment.export(path, format='wav')
        subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path])
        os.remove(path)
        if end_flag:
            self.play_thread = None
    # TODO later, not now
    def stop_playing(self):
        pass

    def play(self):
        if self.play_thread is None:
            thr = Thread(target=lambda: self._play_seg(self.start_var.get() * 1000, self.end_var.get() * 1000, True))
            self.play_thread = thr
            thr.start()

    def play_short(self):
        if self.end_var.get() - self.start_var.get() < 2.4:
            self.play()
            return

        if self.play_thread is None:
            tick = 1  # how many seconds to play
            def play_helper():
                self._play_seg(self.start_var.get() * 1000, self.start_var.get() * 1000 + (tick * 1000), False)
                time.sleep(0.5)
                self._play_seg(self.end_var.get() * 1000 - (tick * 1000), self.end_var.get() * 1000, True)
            thr = Thread(target=play_helper)
            self.play_thread = thr
            thr.start()
        
    def play_last(self, sec_bonus):
        seconds = 1
        if self.play_thread is None:
            start = max(self.end_var.get() * 1000 - (seconds * 1000), self.start_var.get() * 1000)
            thr = Thread(target=lambda: self._play_seg(start, self.end_var.get() * 1000 + (sec_bonus * 1000), True))
            self.play_thread = thr
            thr.start()

    def _save(self):
        item = self.data[SEGMENTS][self.id_curr_seg]
        item[START_SEG] = round(self.start_var.get(), 3)
        item[END_SEG] = round(self.end_var.get(), 3)
        if self.txt.get("1.0", "end-1c") != item[TEXT_SEG]:
            if messagebox.askyesno("Unsaved Text", "You Modified the Text, Wanna save it?"):
                self.save_edited_text()
        self.last_saved_id = item[ID_SEG]

    def save_and_next(self):
        self._save()
        item = self.data[SEGMENTS][self.id_curr_seg]
        self.last_end_time = item[END_SEG]

        self.id_curr_seg += 1
        self.load_segment()

    def leave(self):
        write_the_data_in_subtitle_json(self.folder, self.data)
        print(f"Last edited ID: {self.last_saved_id}")
        self.root.destroy()
        exit(0)

    def extend_end_by_2_sec(self):
        self.disp_end += 2

        width = min(1900, int(((self.disp_end - self.disp_start) / 0.5) * LENGTH_PER_05_SEC))
        self.canvas.config(width=width)

        self.draw_all()
    
    def mark_skipped(self):
        if messagebox.askyesno("Mark SKIPPED", f"Mark this segment as {SKIPPED}?"):
            item = self.data[SEGMENTS][self.id_curr_seg]
            item[TEXT_SEG] = SKIPPED + item[TEXT_SEG].replace(SKIPPED, "")
            self.id_curr_seg += 1
            self.load_segment()
    
    def back(self):
        self.id_curr_seg -= 1
        while str(self.data[SEGMENTS][self.id_curr_seg][TEXT_SEG]).startswith(SKIPPED):
            self.id_curr_seg -= 1
        self.last_end_time = -1
        self.load_segment()

    def move_marker(self, amount):
        if self.select_mark.get() == -1:
            return

        idx = self.select_mark.get()
        obj = self.markers[idx]
        t = obj.get() + amount

        if idx == 0:
            up_obj = self.markers[idx + 1]
            if t < self.disp_start or t >= up_obj.get():
                return
        elif idx == len(self.markers) - 1:
            down_obj = self.markers[idx - 1]
            if t > self.disp_end or down_obj.get() >= t:
                return
        else:
            down_obj = self.markers[idx - 1]
            up_obj = self.markers[idx + 1]
            if t >= up_obj.get() or down_obj.get() >= t:
                return

        obj.set(round(t, 3))
        self.draw_markers()

    def save_edited_text(self):
        if messagebox.askyesno("Modify Text", "You sure you want to modify TEXT?"):
            self.data[SEGMENTS][self.id_curr_seg][TEXT_SEG] = self.txt.get("1.0", "end-1c")

def main():
    if len(sys.argv) == 1:  # TODO needs improvements i think like: (1)-folder_nr (2)7
        nr_working_folder = WORKING_DIR_NUMBER
        start_id = START_EDITING
    else:
        nr_working_folder = int(sys.argv[1])
        start_id = int(sys.argv[2])

    name = get_working_folder_name(nr_working_folder)
    
    audio_path = os.path.join(MY_DATA, name, ".".join(name.split(".")[1:]) + ".mp3")
    audio = AudioSegment.from_mp3(audio_path)

    data = get_the_data_in_subtitle_json(name)
    if isinstance(data[SEGMENTS][0][TEXT_SEG], list):
        print("<><><> Change from List to String <><><>")
        return

    root = tk.Tk()
    Repair_Audio(root, data, audio, name, start_id)
    root.mainloop()

if __name__ == "__main__":
    main()
