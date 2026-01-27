from queue import Queue
from threading import Thread, Semaphore, Event
from tkinter import messagebox
from pydub import AudioSegment
import tkinter as tk
import tkinter.font as tkfont
import numpy as np
import tempfile
import os, re, sys, time, json

import pygame

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

WORKING_DIR_NUMBER = 7
MARGIN = 0.5            # seconds of margin around each segment
LENGTH_PER_05_SEC = 80  # how many pixels per 0.5 seconds
START_EDITING = 0       # from wich ID to start editing

# Info:
# list_time = [[group], [group], ...], each group does not interact with other groups of markers
# each group can containt multiple words: [[t1, ..., tn], ...], example group has (n-1) words
# TODO - recommended to check the code beforehand, it is not tested(too much)

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

def strip_naked(string: str) -> str:
    string = re.sub(r'[.,!?]', ' ', string)
    string = re.sub(r'\s+', ' ', string)
    return string.strip()


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
                self.play_seg(elem[0], elem[1], elem[2])

            self.current_time = -1
            self.done.set()

    def play_seg(self, t1, t2, t_between):
        segment = self.audio[t1 * 1000 : t2 * 1000]
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            path = tmp.name
        segment.export(path, format="wav")

        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if self.stop_play.is_set():
                self.stop_playing()
                os.remove(path)
                return
            self.current_time = round(t1 + pygame.mixer.music.get_pos() / 1000, 3)
            time.sleep(0.05)
        os.remove(path)
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

        # Variables
        self.start_var = tk.DoubleVar()
        self.end_var = tk.DoubleVar()
        self.disp_start: float  # The time margins of the audio drawing(display range)
        self.disp_end: float
        self.txt: tk.Text  # used to modify the TEXT

        # Info purpose
        self.info_text = tk.StringVar() # general info at the top
        self.list_time = tk.StringVar() # time for words in editing faze
        self.list_time_real = tk.StringVar() # time for words from self.data
        self.mrk_VS_word_Label: tk.Label  # set fg: green if good, red if bad
        self.mrk_VS_word = tk.StringVar() # ratio marks/words

        # Markers
        self.NORM_MRK = 0 # this mark + the next -> word sound
        self.END_MRK = 1  # this mark + the next -> not a word sound
        self.markers: list[tuple[tk.DoubleVar, int]]  # tuple(time, tipe_marker)
        self.select_mark = tk.IntVar()  # index of last selected marker
        self.dragging = {'line': None}

        # # Dynamic buttons
        self.dyn_buttons: list[tk.Button] = []
        self.dyn_butt_frame: tk.Frame

        self.upload_widgets()

        # Play threads
        self.list_tasks = Queue()
        self.play = Semaphore(0) # Needs to be released after filling Queue with tasks
        self.done = Event()  # Sygnals that PLAY Queue is free to use
        self.done.set()
        self.suicide = Event()   # Kill thread signal
        self.stop_play = Event() # Stop playing audio
        self.play_thread = Task_Audio_process(self.list_tasks, self.play, self.done, self.suicide, self.stop_play, self.audio)
        self.play_thread.start()

        self.load_segment()

    # --- Main functions ---
    def upload_widgets(self):
        self.root.attributes('-zoomed', True)
        self.root.title("Audio Segment Editor For Each Separate Word")
        self.root.protocol("WM_DELETE_WINDOW", self.leave) # Calls leave() when i press X
        self.root.bind('<Right>', self.sel_next_mrk)
        self.root.bind('<Left>',  self.sel_past_mrk)
        self.root.configure(bg="#1e1e1e")
        label_style = {"bg": "#1e1e1e", "fg": "#ffb347"}
        tk.Label(self.root, textvariable=self.info_text, justify='left', **label_style).pack(pady=5)

        self.canvas = tk.Canvas(self.root, height=160, bg="#7b7b7b")
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
        tk.Label(frame, text="Mrk/Word:", **label_style)             .grid(row=0, column=6, padx=10)
        self.mrk_VS_word_Label = tk.Label(frame, textvariable=self.mrk_VS_word, bg="#1e1e1e")
        self.mrk_VS_word_Label.grid(row=0, column=7, padx=5)

        times = tk.Frame(self.root, bg="#1e1e1e")
        times.pack(pady=5)
        tk.Label(times, textvariable=self.list_time_real, **label_style).pack()
        tk.Label(times, textvariable=self.list_time,      **label_style).pack()

        # Dynamic setup
        self.dyn_butt_frame = tk.Frame(self.root)
        self.dyn_butt_frame.pack(side="top")

        # Normal Buttons
        frame_butt_up = tk.Frame(self.root, bg="#1e1e1e")
        frame_butt_up.pack(side="top")
        frame_aaaa = tk.Frame(self.root, bg="#1e1e1e")
        frame_aaaa.pack(side="top")
        frame_sec_row = tk.Frame(self.root, bg="#1e1e1e")
        frame_sec_row.pack(side="top")
        frame_third_row = tk.Frame(self.root, bg="#1e1e1e")
        frame_third_row.pack(side="top")
        frame_butt_down = tk.Frame(self.root, bg="#1e1e1e")
        frame_butt_down.pack(side="bottom")

        tk.Button(frame_butt_up, text="-0.04",  command=lambda: self.move_marker(-0.04)).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="-0.01",  command=lambda: self.move_marker(-0.01)).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="-0.005", command=lambda: self.move_marker(-0.005)).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="Play",   command=self.play_all).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text=" ■ ",    command=self.stop_playing).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="+0.005", command=lambda: self.move_marker(0.005)).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="+0.01",  command=lambda: self.move_marker(0.01)).pack(pady=2, side='left')
        tk.Button(frame_butt_up, text="+0.04",  command=lambda: self.move_marker(0.04)).pack(pady=2, side='left')

        tk.Button(frame_aaaa, text="Play SHORT", command=self.play_short).pack(pady=2)

        tk.Button(frame_sec_row, text="ADD_Mark",   command=self.add_mark).pack(pady=2, side='left')
        tk.Button(frame_sec_row, text="DEL_Mark",   command=self.del_mark).pack(pady=2, side='left')
        tk.Button(frame_sec_row, text="Separ_Group", command=self.separ_mark).pack(pady=2, side='left')
        tk.Button(frame_sec_row, text="Unite_Group", command=self.unite_mark).pack(pady=2, side='left')
        tk.Button(frame_sec_row, text="ADD_Group", command=self.add_group).pack(pady=2, side='left')
        tk.Button(frame_sec_row, text="DEL_Group", command=self.del_group).pack(pady=2, side='left')
        tk.Button(frame_sec_row, text="UNITE_ALL", command=self.unite_all_groups).pack(pady=2, side='left')

        tk.Button(frame_third_row, text="SaveListTime",  command=self.save_time_words, fg="green").pack(padx=5, side='left')
        tk.Button(frame_third_row, text="Save and Next", command=self.save_and_next, fg="green").pack(pady=2, side='left')
        tk.Button(frame_third_row, text="display -1s",   command=self.disp_start_extend).pack(pady=2, side='left')
        tk.Button(frame_third_row, text="display +1s",   command=self.disp_end_extend).pack(pady=2, side='left')

        tk.Button(frame_butt_down, text="Leave(exit)", command=self.leave, fg="red").pack(pady=2, side='right')
        tk.Button(frame_butt_down, text="Back",        command=self.back).pack(pady=2, side='left')
        tk.Button(frame_butt_down, text="    ҉",       command=self.load_segment).pack(pady=2, side='left')

        text_buttons = tk.Frame(self.root)
        text_buttons.pack(side='bottom')
        tk.Button(text_buttons, text="Save Text", command=self.save_edited_text, fg="green").pack(side='right')
        self.text_butt_access = tk.Button(text_buttons, text="NOT  EDITING", command=self.swich_text_access, bg="#49C826", activebackground="green")
        self.text_butt_access.pack(side='right')

        text_frame = tk.Frame(self.root)
        text_frame.pack(side="bottom")
        big_font = tkfont.Font(family="Consolas", size=14)
        self.txt = tk.Text(text_frame, height=8, width=80, wrap="word", font=big_font,
                           bg="#1e1e1e", fg="#d4a373", insertbackground="#d7c9bb")
        self.txt.pack()
        self.txt.insert(tk.END, self.data[SEGMENTS][self.id_curr_seg][TEXT_SEG])
        self.txt.config(state="disabled")

    def _load_dinamic_widgets(self):
        """Destroys old buttons in dynamic_buttons dict and makes new ones"""
        if len(self.dyn_buttons) != 0:
            for butt in self.dyn_buttons:
                butt.destroy()
        self.dyn_buttons = []

        words = strip_naked(self.data[SEGMENTS][self.id_curr_seg][TEXT_SEG]).split()
        for idx, word in enumerate(words):
            butt = tk.Button(self.dyn_butt_frame, text=word, command=lambda i=idx: self.play_word(i))
            butt.pack(side='left')
            self.dyn_buttons.append(butt)

    def load_segment(self):
        """This function dictates wich segments to edit, can be modified to suit the user's needs"""
        if not (0 <= self.id_curr_seg < len(self.data[SEGMENTS])):
            self.leave()
        item = self.data[SEGMENTS][self.id_curr_seg]
        if LIST_TIME not in self.data[SEGMENTS][self.id_curr_seg]:
            messagebox.showwarning("Warning", "Time for Words Not Existent, Imma leave now")
            self.leave()

        # Variables
        self.start_var.set(item[START_SEG])
        self.end_var.set(item[END_SEG])
        self.select_mark.set(-1)
        self.info_text.set(f'ID: {item[ID_SEG]} | User: {item[ID_USER]} | Text: {item[TEXT_SEG]}')
        self.list_time_real.set(str(item[LIST_TIME]))

        self.disp_start = max(min(self.start_var.get(), item[LIST_TIME][0][0]) - MARGIN, 0)
        self.disp_end = min(max(self.end_var.get(), item[LIST_TIME][-1][-1]) + MARGIN, self.audio.duration_seconds)

        # Change canvas size
        width = min(1900, int(((self.disp_end - self.disp_start) / 0.5) * LENGTH_PER_05_SEC))
        self.canvas.config(width=width)

        # Update Text
        self.txt.delete("1.0", tk.END)
        self.txt.insert(tk.END, item[TEXT_SEG])

        self._load_dinamic_widgets()
        self.define_markers()
        self.update_mrk_Word_info()
        self.draw_all()

    def update_mrk_Word_info(self):
        val_mrk = len(self.markers)
        for val in self.markers:
            if val[1] == self.END_MRK:
                val_mrk -= 1
        val_word = len(strip_naked(self.data[SEGMENTS][self.id_curr_seg][TEXT_SEG]).split())
        if val_word == val_mrk: color = "green"
        else:                   color = "red"
        self.mrk_VS_word_Label.configure(fg=color)
        self.mrk_VS_word.set(f'{val_mrk}/{val_word}')

    def define_markers(self):
        self.markers = []
        item = self.data[SEGMENTS][self.id_curr_seg]

        last_val = -1
        for lst in item[LIST_TIME]:
            for index in range(len(lst)-1):
                if last_val < lst[index]:
                    last_val = lst[index]
                else:
                    if len(self.markers) > 0 and self.markers[-1][1] == self.END_MRK:
                        self.markers[-1] = (self.markers[-1][0], self.NORM_MRK)
                        continue
                    else: last_val += 0.1
                self.markers.append((tk.DoubleVar(self.root, last_val), self.NORM_MRK))
            # End Mark
            if last_val < lst[-1]:
                last_val = lst[-1]
            else: last_val += 0.1
            self.markers.append((tk.DoubleVar(self.root, last_val), self.END_MRK))

    def draw_markers(self):
        self.canvas.delete('marker')
        self.canvas.delete('selection')
        self.canvas.delete('marker_text')
        self.canvas.delete('marker_dead')

        canv_height, canv_width = self.canvas.winfo_height(), self.canvas.winfo_width()
        duration = self.disp_end - self.disp_start

        # Mark start/end
        x_s = int(((self.start_var.get() - self.disp_start) / duration) * canv_width)
        x_e = int(((self.end_var.get()   - self.disp_start) / duration) * canv_width)
        self.canvas.create_line(x_s, 0, x_s, canv_height, width=2, tags='marker_dead', fill="#F3A3F3")
        self.canvas.create_line(x_e, 0, x_e, canv_height, width=2, tags='marker_dead', fill="#F3A3F3")

        fill_opt = ["#FF7F50", "#9370DB","#FFD700", "skyblue"]
        fill_idx = 0
        # Draw Markers
        x_past = -1
        for idx, mrk in enumerate(self.markers):
            x = int(((mrk[0].get() - self.disp_start) / duration) * canv_width)
            self.canvas.create_line(x, 0, x, canv_height, width=2, tags=('marker', f'marker_{idx}'))
            self.canvas.create_text(x + 4, 4, text=f"{mrk[0].get():.3f}s", anchor='nw', tags='marker_text')
            if x_past != -1:
                self.canvas.create_rectangle(x_past, 0, x, canv_height, fill=fill_opt[fill_idx], stipple='gray12', width=0, tags='selection')
                fill_idx = (fill_idx + 1) % len(fill_opt)
            
            if mrk[1] == self.END_MRK: x_past = -1
            else:                      x_past = x
        
        self.canvas.itemconfig('marker', fill="#49E949")
        if self.select_mark.get() != -1:
            self.canvas.itemconfig(f'marker_{self.select_mark.get()}', fill='red')

        self.list_time.set(str(self.mrks_to_list()))

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

    def mrks_to_list(self) -> list[list[float]]:
        ret_list = []
        temp_list = []
        for val in self.markers:
            temp_list.append(val[0].get())
            if val[1] == self.END_MRK:
                ret_list.append(temp_list)
                temp_list = []
        return ret_list
    
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
        obj = self.markers[idx][0]

        if idx == 0:
            up_obj = self.markers[idx + 1][0]
            if t < self.disp_start or t >= up_obj.get():
                return
        elif idx == len(self.markers) - 1:
            down_obj = self.markers[idx - 1][0]
            if t > self.disp_end or down_obj.get() >= t:
                return
        else:
            down_obj = self.markers[idx - 1][0]
            up_obj = self.markers[idx + 1][0]
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

    def play_all(self):
        if not self.done.is_set():
            return
        self.done.clear()
        idx = 1
        while idx < len(self.markers):
            obj      = self.markers[idx]
            obj_back = self.markers[idx - 1]

            if idx == len(self.markers) - 1: tm_between = 0
            else:                            tm_between = 0.3

            self.list_tasks.put((obj_back[0].get(), obj[0].get(), tm_between))
            if obj[1] == self.END_MRK:
                idx += 1
            idx += 1
        self.play.release()
        self.draw_moving_mark()

    def play_short(self):
        if self.select_mark.get() == -1 or not self.done.is_set():
            return
        self.done.clear()

        tick = 0.5  # how many seconds to play at margins
        idx_mid = self.select_mark.get()
        time_mid = self.markers[idx_mid][0].get()
        if idx_mid == 0:
            time_first = time_mid - tick
            time_last = self.markers[idx_mid + 1][0].get()
        elif idx_mid == len(self.markers) - 1:
            time_first = self.markers[idx_mid - 1][0].get()
            time_last = time_mid + tick
        else:
            time_first = self.markers[idx_mid - 1][0].get()
            time_last = self.markers[idx_mid + 1][0].get()

        self.list_tasks.put((time_first, time_mid, 0.5))
        self.list_tasks.put((time_mid, time_last, 0))

        self.play.release()
        self.draw_moving_mark()

    def play_word(self, nr_word):
        if not self.done.is_set():
            return
        self.done.clear()

        idx_word = -1  # index pointing to start mrk for word
        my_nr_word = 0
        for idx, mrk in enumerate(self.markers):
            if mrk[1] == self.END_MRK:
                my_nr_word -= 1
            if my_nr_word == nr_word:
                idx_word = idx
                break
            my_nr_word += 1
        if idx_word == -1 or idx_word >= len(self.markers) - 1:
            self.done.set()
            return

        self.list_tasks.put((self.markers[idx_word][0].get(),
                             self.markers[idx_word + 1][0].get(), 0))
        self.play.release()
        self.draw_moving_mark()

    def _save(self):
        item = self.data[SEGMENTS][self.id_curr_seg]
        if self.txt.get("1.0", "end-1c") != item[TEXT_SEG]:
            self.save_edited_text()
        self.save_time_words()
        self.last_saved_id = item[ID_SEG]

    def save_and_next(self):
        self._save()

        self.id_curr_seg += 1
        self.load_segment()

    def leave(self):
        self.stop_playing() # kill Thread
        self.suicide.set()
        self.play.release()

        write_the_data_in_subtitle_json(self.folder, self.data)
        print(f"Last edited ID: {self.last_saved_id}")
        self.root.destroy()
        exit(0)

    def back(self):
        self.id_curr_seg -= 1
        self.load_segment()

    def move_marker(self, amount):
        if self.select_mark.get() == -1:
            return

        idx = self.select_mark.get()
        obj = self.markers[idx][0]
        t = round(obj.get() + amount, 3)

        if idx == 0:
            up_obj = self.markers[idx + 1][0]
            if t < self.disp_start or t >= up_obj.get():
                return
        elif idx == len(self.markers) - 1:
            down_obj = self.markers[idx - 1][0]
            if t > self.disp_end or down_obj.get() >= t:
                return
        else:
            down_obj = self.markers[idx - 1][0]
            up_obj = self.markers[idx + 1][0]
            if t >= up_obj.get() or down_obj.get() >= t:
                return

        obj.set(t)
        self.draw_markers()

    def save_edited_text(self):
        item = self.data[SEGMENTS][self.id_curr_seg]
        item[TEXT_SEG] = self.txt.get("1.0", "end-1c")
        self.info_text.set(f'ID: {item[ID_SEG]} | User: {item[ID_USER]} | Text: {item[TEXT_SEG]}')
        self._load_dinamic_widgets()

    def unite_mark(self):
        """Keep selected Marker time and remove the other"""
        if self.select_mark.get() == -1:
            return
        obj = self.markers[self.select_mark.get()]

        if obj[1] == self.NORM_MRK: # look back for END_mark
            if self.select_mark.get() == 0: return
            back_obj = self.markers[self.select_mark.get() - 1]
            if back_obj[1] != self.END_MRK: return

            self.markers.pop(self.select_mark.get() - 1)
        else: # look ahead for NORMAL_mark
            if self.select_mark.get() == len(self.markers) - 1: return

            self.markers.pop(self.select_mark.get() + 1)
            self.markers[self.select_mark.get()] = (obj[0], self.NORM_MRK)

        self.draw_markers()
        self.update_mrk_Word_info()

    def separ_mark(self):
        if self.select_mark.get() == -1:
            return
        obj = self.markers[self.select_mark.get()]
        if obj[1] == self.END_MRK or self.select_mark.get() == 0:
            return
        before_obj = self.markers[self.select_mark.get() - 1]
        if before_obj[1] == self.END_MRK:
            return
        # Make new marker
        next_obj = self.markers[self.select_mark.get() + 1]
        new_time = round(obj[0].get() + (next_obj[0].get() - obj[0].get()) / 2, 3)
        new_obj = (tk.DoubleVar(self.root, new_time), self.NORM_MRK)
        # Modify markers list
        self.markers.insert(self.select_mark.get() + 1, new_obj)
        self.markers[self.select_mark.get()] = (obj[0], self.END_MRK)
        self.draw_markers()
        self.update_mrk_Word_info()

    def add_mark(self):
        if self.select_mark.get() == -1:
            return
        obj = self.markers[self.select_mark.get()]
        if obj[1] == self.END_MRK:
            if self.select_mark.get() == len(self.markers) - 1:
                next_time = self.disp_end  # if no more markers after
            else:
                next_time = self.markers[self.select_mark.get() + 1][0].get()
            mrk_type = self.END_MRK
            self.markers[self.select_mark.get()] = (obj[0], self.NORM_MRK)
        else:
            next_time = self.markers[self.select_mark.get() + 1][0].get()
            mrk_type = self.NORM_MRK
            
        new_time = round(obj[0].get() + (next_time - obj[0].get()) / 2, 3)
        self.markers.insert(self.select_mark.get() + 1, (tk.DoubleVar(self.root, new_time), mrk_type))
        self.draw_markers()
        self.update_mrk_Word_info()

    def del_mark(self):
        if self.select_mark.get() == -1:
            return
        obj = self.markers[self.select_mark.get()]
        # check if group >= 3 members
        if obj[1] == self.END_MRK:
            nr_members = 1
            for idx in range(self.select_mark.get() - 1, -1, -1):
                if self.markers[idx][1] == self.END_MRK:
                    break
                nr_members += 1
        else:
            nr_members = 0 # count +1 End, count -1 repetitive center
            for idx in range(self.select_mark.get(), -1, -1):
                if self.markers[idx][1] == self.END_MRK:
                    break
                nr_members += 1
            for idx in range(self.select_mark.get(), len(self.markers)):
                if self.markers[idx][1] == self.END_MRK:
                    break
                nr_members += 1
        if nr_members < 3: return

        if obj[1] == self.END_MRK:
            obj_back = self.markers[self.select_mark.get() - 1]
            self.markers[self.select_mark.get() - 1] = (obj_back[0], self.END_MRK)
        
        self.markers.pop(self.select_mark.get())
        self.draw_markers()
        self.update_mrk_Word_info()

    def add_group(self):
        last = self.markers[-1]
        self.markers.append((tk.DoubleVar(self.root, round(last[0].get() + 0.1, 3)), self.NORM_MRK))
        self.markers.append((tk.DoubleVar(self.root, round(last[0].get() + 0.2, 3)), self.END_MRK))

        self.draw_markers()
        self.update_mrk_Word_info()

    def del_group(self):
        if self.select_mark.get() == -1:
            return
        obj = self.markers[self.select_mark.get()]
        if obj[1] == self.END_MRK:
            end_idx = self.select_mark.get()
        else:
            for idx in range(self.select_mark.get() + 1, len(self.markers)):
                if self.markers[idx][1] == self.END_MRK:
                    end_idx = idx
                    break

        for idx in range(end_idx - 1, -1, -1):
            if self.markers[idx][1] == self.END_MRK:
                beg_idx = idx + 1
                break
        else:
            beg_idx = 0
        
        for _ in range(end_idx - beg_idx + 1):
            self.markers.pop(beg_idx)
        self.draw_markers()
        self.update_mrk_Word_info()

    def unite_all_groups(self):
        idx = 0
        while idx < len(self.markers) - 1:
            if self.markers[idx][1] == self.END_MRK:
                self.markers.pop(idx)
                continue
            idx += 1
        self.draw_markers()
        self.update_mrk_Word_info()

    def disp_end_extend(self):
        self.disp_end += 1

        width = min(1900, int(((self.disp_end - self.disp_start) / 0.5) * LENGTH_PER_05_SEC))
        self.canvas.config(width=width)

        self.draw_all()

    def disp_start_extend(self):
        self.disp_start -= 1

        width = min(1900, int(((self.disp_end - self.disp_start) / 0.5) * LENGTH_PER_05_SEC))
        self.canvas.config(width=width)

        self.draw_all()

    def save_time_words(self):
        item = self.data[SEGMENTS][self.id_curr_seg]
        item[LIST_TIME] = self.mrks_to_list()
        self.list_time_real.set(str(item[LIST_TIME]))

    def swich_text_access(self):
        if self.txt['state'] == 'disabled':
            self.txt.config(state="normal")
            self.text_butt_access.config(text="EDITING TEXT", bg="red", activebackground="#D23A3A")
        else:
            self.txt.config(state="disabled")
            self.text_butt_access.config(text="NOT  EDITING", bg="#49C826", activebackground="green")

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

    root = tk.Tk()
    Repair_Audio(root, data, audio, name, start_id)
    root.mainloop()


if __name__ == "__main__":
    main()
