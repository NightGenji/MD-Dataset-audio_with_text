import io
import os
import sys
import json
import copy
import time
import pygame
import tempfile
import pedalboard
import numpy as np
import tkinter as tk
import tkinter.font as tkfont

from queue import Queue
from threading import Thread
from tkinter import messagebox
from pydub import AudioSegment
from threading import Thread, Semaphore, Event

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

# visual audio drawing parameters
MARGIN = 1.5
LENGTH_PER_05_SEC = 50  # pixels per 0.5 sec
# from wich ID to start editing
WORKING_DIR_NUMBER = 1
START_EDITING = 294

"""first arg  -> takes a WORKING_DIR_NUMBER value"""
"""second arg -> takes a START_EDITING value"""


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

def rewrite_id_segments(data):
    for idx in range(len(data[SEGMENTS])):
        data[SEGMENTS][idx][ID_SEG] = idx


class Task_Audio_process(Thread):
    def __init__(self,
                 list_tasks: Queue,
                 play: Semaphore,
                 done: Event,
                 suicide: Event,
                 stop_play: Event,
                 audio: AudioSegment):
        super().__init__()
        self.list_tasks = list_tasks
        self.play = play  # in main release after puting tasks in Queue
        self.done = done  # signals that i can modify Queue - add new tasks
        self.suicide = suicide  # in main at leave() function play.release() + activate suicide
        self.audio = audio
        self.stop_play = stop_play  # flag to stop audio play
        self.current_time = -1

        pygame.mixer.init()
    
    def run(self):
        while True:
            self.play.acquire()
            self.stop_play.clear()

            if self.suicide.is_set(): break
            while not self.list_tasks.empty():
                elem = self.list_tasks.get()
                if len(elem) == 4:
                    self.play_seg(elem[0], elem[1], elem[2], elem[3])
                else:
                    self.play_seg(elem[0], elem[1], elem[2])

            self.current_time = -1
            self.done.set()

    def play_seg(self, t1, t2, t_between, speed: float = 1.0):
        segment = self.audio[int(t1 * 1000) : int(t2 * 1000)]

        if speed != 1.0:
            samples = np.array(segment.get_array_of_samples()).astype(np.float32) / 32768.0
            if segment.channels > 1:
                samples = samples.reshape((-1, segment.channels)).T
            else:
                samples = samples.reshape((1, -1))

            stretched = pedalboard.time_stretch(samples, segment.frame_rate, speed)
            if segment.channels > 1:
                stretched = stretched.T
                
            rescaled = (stretched * 32767).astype(np.int16)
            segment = AudioSegment(
                rescaled.tobytes(),
                frame_rate=segment.frame_rate,
                sample_width=2,
                channels=segment.channels
            )

        wav_io = io.BytesIO()
        segment.export(wav_io, format="wav")
        wav_io.seek(0)  # Rewind to start of virtual file

        pygame.mixer.music.load(wav_io)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            if self.stop_play.is_set():
                self.stop_playing()
                return
            self.current_time = round(t1 + pygame.mixer.music.get_pos() * speed / 1000, 3)
            time.sleep(0.05)
        
        time.sleep(t_between)  # time between plays

    def stop_playing(self):
        while not self.list_tasks.empty(): # Empty tasks
            self.list_tasks.get_nowait()
        if pygame.mixer.music.get_busy(): # Stop audio
            pygame.mixer.music.stop()


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
        self.txt_past: tk.Text  # used to modify TEXT for segments
        self.txt_curr: tk.Text
        self.txt_next: tk.Text
        self.last_focused_text = None

        # The time margins of the audio drawing
        self.disp_start: float
        self.disp_end: float

        # Markers
        self.markers: list[tk.DoubleVar]
        self.select_mark = tk.IntVar()  # index of last selected marker
        self.dragging = {'line': None}

        # Play threads
        self.list_tasks = Queue()
        self.play = Semaphore(0) # Needs to be released after filling Queue with tasks
        self.done = Event()  # Sygnals that PLAY Queue is free to use
        self.done.set()
        self.suicide = Event()   # Kill thread signal
        self.stop_play = Event() # Stop playing audio
        self.play_thread = Task_Audio_process(self.list_tasks, self.play, self.done, self.suicide, self.stop_play, self.audio)
        self.play_thread.start()

        self.upload_widgets()
        self.brain()

    # --- Main functions ---
    def upload_widgets(self):
        self.root.attributes('-zoomed', True)
        self.root.title("Editing Segment Time")
        self.root.protocol("WM_DELETE_WINDOW", self.leave) # Calls leave() when i press X
        self.root.bind('<Right>', self.sel_next_mrk)
        self.root.bind('<Left>',  self.sel_past_mrk)
        self.root.configure(bg="#1e1e1e")
        label_style = {"bg": "#1e1e1e", "fg": "#ffb347"}
        tk.Label(self.root, textvariable=self.info_text, justify='left', **label_style).pack(pady=5)

        self.canvas = tk.Canvas(self.root, height=140, bg="#7b7b7b")
        self.canvas.pack()
        self.canvas.bind('<Button-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_motion)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)

        frame = tk.Frame(self.root, bg="#1e1e1e")
        frame.pack(pady=5)
        tk.Label(frame, text="Start (s):", **label_style)            .grid(row=0, column=0)
        tk.Label(frame, textvariable=self.start_var, **label_style)  .grid(row=0, column=1, padx=5)
        tk.Label(frame, text="End (s):", **label_style)              .grid(row=0, column=2, padx=10)
        tk.Label(frame, textvariable=self.end_var, **label_style)    .grid(row=0, column=3, padx=5)
        tk.Label(frame, text="Idx_Mrk:", **label_style)              .grid(row=0, column=4, padx=10)
        tk.Label(frame, textvariable=self.select_mark, **label_style).grid(row=0, column=5, padx=5)

        frame_butt_up = tk.Frame(self.root, bg="#1e1e1e")
        frame_butt_up.pack(side="top")
        frame_sec_row = tk.Frame(self.root, bg="#1e1e1e")
        frame_sec_row.pack(side="top")
        frame_3rd_row = tk.Frame(self.root, bg="#1e1e1e")
        frame_3rd_row.pack(side="top")
        frame_4th_row = tk.Frame(self.root, bg="#1e1e1e")
        frame_4th_row.pack(side="top")
        frame_butt_down = tk.Frame(self.root, bg="#1e1e1e")
        frame_butt_down.pack(side="bottom")

        tk.Button(frame_butt_up, text="-0.04",  command=lambda: self.move_marker(-0.04)).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="-0.01",  command=lambda: self.move_marker(-0.01)).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="-0.005", command=lambda: self.move_marker(-0.005)).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="Play",   command=self.play_full).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text=" ■ ",    command=self.stop_playing).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="+0.005", command=lambda: self.move_marker(0.005)).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="+0.01",  command=lambda: self.move_marker(0.01)).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="+0.04",  command=lambda: self.move_marker(0.04)).pack(pady=2, side='left')

        tk.Button(frame_sec_row, text="Play_last 1",   command=lambda: self.play_last(0)).pack(pady=2, side='left')
        tk.Button(frame_sec_row, text="Play x0.7",     command=lambda: self.play_full(0.7)).pack(pady=2, side='left')
        tk.Button(frame_sec_row, text="Play SHORT",    command=self.play_short).pack(pady=2, side='left')
        tk.Button(frame_sec_row, text="Play 50%",      command=lambda: self.play_percent(0.5)).pack(pady=2, side='left')
        tk.Button(frame_sec_row, text="Play x1.5",     command=lambda: self.play_full(1.5)).pack(pady=2, side='left')
        tk.Button(frame_sec_row, text="Play_last 1.1", command=lambda: self.play_last(0.1)).pack(pady=2, side='left')

        tk.Button(frame_3rd_row, text="Save and Next", command=self.save_and_next, fg="green").pack(pady=2)

        tk.Button(frame_4th_row, text="Delete Seg",    command=self.delete_segment).pack(pady=2, side='left')
        tk.Button(frame_4th_row, text="Join Seg",      command=self.join_segments).pack(pady=2, side='left')
        tk.Button(frame_4th_row, text="Dublicate Seg", command=self.dublicate_segment).pack(pady=2, side='left')
        tk.Button(frame_4th_row, text="+2 sec",        command=self.extend_end_by_2_sec).pack(pady=2, side='left')

        tk.Button(frame_butt_down, text="Leave(exit)",  command=self.leave, fg="red").pack(pady=2, side='right')
        tk.Button(frame_butt_down, text="Mark SKIPPED", command=self.mark_skipped, fg="red").pack(pady=2, side='right')
        tk.Button(frame_butt_down, text="    ҉",        command=self.brain).pack(pady=2, side='left')
        tk.Button(frame_butt_down, text="Back",         command=self.back).pack(pady=2, side='left')

        text_buttons = tk.Frame(self.root)
        text_buttons.pack(side='bottom')
        tk.Button(text_buttons, text="Save Text", command=self.save_edited_text, fg="green").pack(side='right')
        self.text_butt_access = tk.Button(text_buttons, text="NOT  EDITING", command=self.swich_text_access, bg="#49C826", activebackground="green")
        self.text_butt_access.pack(side='right')

        text_frame = tk.Frame(self.root)
        text_frame.pack(side="bottom")
        big_font = tkfont.Font(family="Consolas", size=14)

        # Special Characters Fix
        ro_frame = tk.Frame(text_frame)
        ro_frame.pack(side='right', padx=4, fill='y', expand=True)
        ro_chars = ['ă', 'â', 'î', 'ș', 'ț']
        for char in ro_chars:
            btn = tk.Button(ro_frame, text=char, width=1, font=("Arial", 10, "bold"),
                            command=lambda c=char: self.insert_ro_char(c))
            btn.pack(side='top', anchor='n', padx=2, pady=4)
        
        ro_chars = ['Ț', 'Ș', 'Î', 'Â', 'Ă']
        for char in ro_chars:
            btn = tk.Button(ro_frame, text=char, width=1, font=("Arial", 10, "bold"),
                            command=lambda c=char: self.insert_ro_char(c))
            btn.pack(side='bottom', anchor='s', padx=2, pady=4)

        # Text Past
        self.txt_past = tk.Text(text_frame, height=8, width=80, wrap="word", font=big_font,
                           bg="#1e1e1e", fg="#d4a373", insertbackground="#d7c9bb")
        self.txt_past.pack()
        self.txt_past.insert(tk.END, self._return_text_value_or_default(self.id_curr_seg - 1))
        self.txt_past.config(state="disabled")
        self.txt_past.bind("<FocusIn>", self._on_text_focus)

        # Text Present
        self.txt_curr = tk.Text(text_frame, height=8, width=80, wrap="word", font=big_font,
                           bg="#1e1e1e", fg="#d4a373", insertbackground="#d7c9bb")
        self.txt_curr.pack()
        self.txt_curr.insert(tk.END, self.data[SEGMENTS][self.id_curr_seg][TEXT_SEG])
        self.txt_curr.config(state="disabled")
        self.txt_curr.bind("<FocusIn>", self._on_text_focus)

        # Text Future
        self.txt_next = tk.Text(text_frame, height=8, width=80, wrap="word", font=big_font,
                           bg="#1e1e1e", fg="#d4a373", insertbackground="#d7c9bb")
        self.txt_next.pack()
        self.txt_next.insert(tk.END, self._return_text_value_or_default(self.id_curr_seg + 1))
        self.txt_next.config(state="disabled")
        self.txt_next.bind("<FocusIn>", self._on_text_focus)

    def _return_text_value_or_default(self, idx):
        if self._within_limits(idx):
            return self.data[SEGMENTS][idx][TEXT_SEG]
        return ""
    
    def _within_limits(self, idx):
        if 0 <= idx and idx < len(self.data[SEGMENTS]):
            return True
        return False

    def brain(self):
        self.load_segment()

    def load_segment_cut_long_segments(self):
        # find segment, if last_saved == -1 , search from begining else from last_saved + 1, take in consideration list_idx-es if empty or not
        # if i agree to cut, i specify how many similar dubs to exist
        # i put the dubs idx in a list and loop through them to edit them all
        # when list is empty i continue with the process until end
        pass

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
        # self.start_var.set(item[START_SEG] if self.last_end_time == -1 else self.last_end_time)
        self.start_var.set(item[START_SEG])

        self.end_var.set(item[END_SEG])
        self.info_text.set(f'ID: {item[ID_SEG]} | User: {item[ID_USER]} | Text: {item[TEXT_SEG]}')
        self.select_mark.set(-1)

        self.disp_start = max(self.start_var.get() - MARGIN, 0)
        self.disp_end = min(self.end_var.get() + MARGIN, self.audio.duration_seconds)

        # Change canvas size
        width = min(1900, int(((self.disp_end - self.disp_start) / 0.5) * LENGTH_PER_05_SEC))
        self.canvas.config(width=width)

        # Update Text
        if self.txt_curr['state'] == 'disabled':
            self.swich_text_access()
        self.txt_past.delete("1.0", tk.END)
        self.txt_past.insert(tk.END, self._return_text_value_or_default(self.id_curr_seg - 1))
        self.txt_curr.delete("1.0", tk.END)
        self.txt_curr.insert(tk.END, item[TEXT_SEG])
        self.txt_next.delete("1.0", tk.END)
        self.txt_next.insert(tk.END, self._return_text_value_or_default(self.id_curr_seg + 1))
        # self.swich_text_access()

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
        
        self.canvas.itemconfig('marker', fill="#49E949")
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
            self.canvas.create_line(x, 0, x, canvas_height, fill="#BDF7B8", dash=(2, 2), tags='drawing')
            self.canvas.create_text(x + 2, canvas_height - 10, text=f"{t:.3f}", anchor='nw', tags='drawing', font=("Arial", 6))
        
        self.draw_markers()

    # --- Mouse Events ---
    def on_press(self, event: tk.Event):
        min_val = 15  # min distance from marker to be selected
        idx_target = -1
        for idx, _ in enumerate(self.markers):
            coords = self.canvas.coords(f'marker_{idx}')
            distance = abs(event.x - coords[0])
            if distance < min_val:
                min_val = distance
                idx_target = idx
        
        if idx_target == -1: return
        self.dragging['line'] = f'marker_{idx_target}'
        if self.select_mark.get() != -1:
            self.canvas.itemconfig(f'marker_{self.select_mark.get()}', fill="#49E949")
        self.select_mark.set(idx_target)
        self.canvas.itemconfig(f'marker_{idx_target}', fill='red')

    def on_motion(self, event: tk.Event):
        if not (0 <= event.x <= self.canvas.winfo_width()):
            return
        tag: str = self.dragging['line']
        if not tag: return

        duration = self.disp_end - self.disp_start
        t = round(self.disp_start + (event.x / self.canvas.winfo_width()) * duration, 3)
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

        obj.set(t)
        self.draw_markers()

    def on_release(self, event: tk.Event):
        self.dragging['line'] = None

    # --- Keyboard Events ---
    def sel_past_mrk(self, event):
        self.select_mark.set(self.select_mark.get() - 1)
        if self.select_mark.get() < 0:
            self.select_mark.set(len(self.markers) - 1)
        self.draw_markers()

    def sel_next_mrk(self, event):
        self.select_mark.set(self.select_mark.get() + 1)
        if self.select_mark.get() == len(self.markers):
            self.select_mark.set(0)
        self.draw_markers()

    # --- Button functions ---
    def stop_playing(self):
        self.stop_play.set()

    def play_full(self, speed: float = 1.0):
        if not self.done.is_set():
            return
        self.done.clear()

        self.list_tasks.put((self.start_var.get(), self.end_var.get(), 0, speed))
        
        self.play.release()
        self.draw_moving_mark()

    def play_short(self):
        if not self.done.is_set():
            return
        self.done.clear()

        if self.end_var.get() - self.start_var.get() < 2.4:
            self.list_tasks.put((self.start_var.get(), self.end_var.get(), 0))
        else:
            tick = 1  # how many seconds to play
            self.list_tasks.put((self.start_var.get(),
                                 self.start_var.get() + tick,
                                 0.5))
            self.list_tasks.put((self.end_var.get() - tick,
                                 self.end_var.get(),
                                 0))
        
        self.play.release()
        self.draw_moving_mark()
        
    def play_last(self, sec_bonus):
        if not self.done.is_set():
            return
        self.done.clear()

        seconds = 1
        start = max(self.end_var.get() - seconds, self.start_var.get())
        
        self.list_tasks.put((start, self.end_var.get() + sec_bonus, 0))

        self.play.release()
        self.draw_moving_mark()

    def play_percent(self, percent):
        if not self.done.is_set():
            return
        self.done.clear()

        time_play = round((self.end_var.get() - self.start_var.get()) * percent, 3)
        self.list_tasks.put((self.end_var.get() - time_play, self.end_var.get(), 0))

        self.play.release()
        self.draw_moving_mark()

    def _save(self):
        item = self.data[SEGMENTS][self.id_curr_seg]
        item[START_SEG] = round(self.start_var.get(), 3)
        item[END_SEG] = round(self.end_var.get(), 3)
        self.save_edited_text()
        self.last_saved_id = item[ID_SEG]

    def save_and_next(self):
        self._save()
        item = self.data[SEGMENTS][self.id_curr_seg]
        self.last_end_time = item[END_SEG]

        self.id_curr_seg += 1
        self.brain()

    def leave(self):
        self.stop_playing() # kill Thread
        self.suicide.set()
        self.play.release()

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
            self.brain()
    
    def back(self):
        self.id_curr_seg -= 1
        while str(self.data[SEGMENTS][self.id_curr_seg][TEXT_SEG]).startswith(SKIPPED):
            self.id_curr_seg -= 1
        self.last_end_time = -1
        self.brain()

    def move_marker(self, amount):
        if self.select_mark.get() == -1:
            return

        idx = self.select_mark.get()
        obj = self.markers[idx]
        t = round(obj.get() + amount, 3)

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

        obj.set(t)
        self.draw_markers()

    def save_edited_text(self):
        if self._within_limits(self.id_curr_seg - 1):
            self.data[SEGMENTS][self.id_curr_seg - 1][TEXT_SEG] = " ".join((self.txt_past.get("1.0", "end-1c")).split())
        if self._within_limits(self.id_curr_seg + 1):
            self.data[SEGMENTS][self.id_curr_seg + 1][TEXT_SEG] = " ".join((self.txt_next.get("1.0", "end-1c")).split())

        item = self.data[SEGMENTS][self.id_curr_seg]
        item[TEXT_SEG] = " ".join((self.txt_curr.get("1.0", "end-1c")).split())

        self.info_text.set(f'ID: {item[ID_SEG]} | User: {item[ID_USER]} | Text: {item[TEXT_SEG]}')

    def swich_text_access(self):
        if self.txt_curr['state'] == 'disabled':
            self.txt_past.config(state="normal")
            self.txt_curr.config(state="normal")
            self.txt_next.config(state="normal")
            self.text_butt_access.config(text="EDITING TEXT", bg="red", activebackground="#D23A3A")
        else:
            self.txt_past.config(state="disabled")
            self.txt_curr.config(state="disabled")
            self.txt_next.config(state="disabled")
            self.text_butt_access.config(text="NOT  EDITING", bg="#49C826", activebackground="green")

    def join_segments(self):
        """Current segment + next segment => make just one segment"""
        if not messagebox.askyesno("Confirm Join", "Will you marry me?"):
            return

        if not self._within_limits(self.id_curr_seg + 1):
            return
        
        item = self.data[SEGMENTS][self.id_curr_seg]
        next = self.data[SEGMENTS][self.id_curr_seg + 1]

        if item[ID_USER] != next[ID_USER]:
            return
        
        # join time and words
        item[END_SEG] = next[END_SEG]
        words = (item[TEXT_SEG] + " " + next[TEXT_SEG]).split()
        item[TEXT_SEG] = " ".join(words)
        # delete next
        self.data[SEGMENTS].pop(self.id_curr_seg + 1)

        rewrite_id_segments(self.data)
        self.brain()

    def delete_segment(self):
        if not messagebox.askyesno("Confirm Delete", "Kboom Rico?"):
            return

        self.data[SEGMENTS].pop(self.id_curr_seg)

        rewrite_id_segments(self.data)
        self.brain()

    def dublicate_segment(self):
        if not messagebox.askyesno("Confirm Dublicate", "I'd clone your mother if I could"):
            return

        new_seg = copy.deepcopy(self.data[SEGMENTS][self.id_curr_seg])
        self.data[SEGMENTS].insert(self.id_curr_seg, new_seg)

        rewrite_id_segments(self.data)
        self.brain()

    def _on_text_focus(self, event):
        self.last_focused_text = event.widget

    def insert_ro_char(self, char):
        if self.last_focused_text and self.last_focused_text['state'] != 'disabled':
            self.last_focused_text.insert(tk.INSERT, char)  # insert where cursor is
            self.last_focused_text.focus_set()  # Move focus back to text box immediately

    def draw_moving_mark(self):
        self.canvas.delete('moving_marker')
        if self.done.is_set():
            return
        
        if self.play_thread.current_time != -1:
            x = int(((self.play_thread.current_time - self.disp_start) / (self.disp_end - self.disp_start)) * self.canvas.winfo_width())
            self.canvas.create_line(x, 0, x, self.canvas.winfo_height(), width=2, tags='moving_marker', fill="#9727FF")

        self.root.after(40, self.draw_moving_mark)


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

    # order the ID's in order
    rewrite_id_segments(data)

    root = tk.Tk()
    Repair_Audio(root, data, audio, name, start_id)
    root.mainloop()


if __name__ == "__main__":
    main()
