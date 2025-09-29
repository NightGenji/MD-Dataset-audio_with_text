import sys
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

WORKING_DIR_NUMBER = 7
MARGIN = 1.5            # seconds of margin around each segment
LENGTH_PER_05_SEC = 50  # how many pixels per 0.5 seconds
START_EDITING = 0    # from wich ID to start editing

"""this script takes a WORKING_DIR_NUMBER value as first argument if any"""
"""then it takes a START_EDITING value as a second argument if any"""
# TODO and make it able edit the text as well

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

def brain():
    if len(sys.argv) == 1:
        start_edit_nr = START_EDITING
        working_dirNr = WORKING_DIR_NUMBER
    else:
        working_dirNr = int(sys.argv[1])
        start_edit_nr = int(sys.argv[2])
    name = get_working_folder_name(working_dirNr)
    data = get_the_data_in_subtitle_json(name)

    # Load audio
    audio_path = MY_DATA + name + '/' + ".".join(name.split(".")[1:]) + ".mp3"
    audio = AudioSegment.from_mp3(audio_path)
    total_duration = audio.duration_seconds
    last_time = -1
    last_edited_id = -1

    ind_el = 0
    while ind_el < len(data["segments"]) and data["segments"][ind_el]["id"] < start_edit_nr:
        ind_el += 1

    while ind_el < len(data["segments"]):
        item = data["segments"][ind_el]

        if last_time != -1:
            segment_start = last_time
        else:
            segment_start = item["start"]
        segment_end = item["end"]
        if str(item["text"]).startswith("SKIPPED-- "):
            ind_el += 1
            continue
        if segment_start > segment_end:
            item["text"] = "SKIPPED-- " + item["text"]
            ind_el += 1
            continue
        text = item["text"]
        id_user = item["id_user"]
        segment_id = item["id"]
        done = [False]

        def launch_gui():
            win = tk.Tk()
            win.title(f"Editing Segment ID {segment_id}")

            # Info
            tk.Label(win, text=f"ID: {segment_id} | User: {id_user}\n{text}", justify='left').pack(pady=5)

            disp_start = max(segment_start - MARGIN, 0)
            disp_end = min(segment_end + MARGIN, total_duration)
            duration = disp_end - disp_start
            canvas_width, canvas_height = min(1900, int((duration / 0.5) * LENGTH_PER_05_SEC)), 140

            # Variables
            start_var = tk.DoubleVar(value=segment_start)
            end_var = tk.DoubleVar(value=segment_end)
            text_var = tk.StringVar(value=text)
            dragging = {'line': None}

            # Draw canvas
            canvas = tk.Canvas(win, width=canvas_width, height=canvas_height, bg='white')
            canvas.pack()

            # Waveform
            display_audio = audio[int(disp_start * 1000):int(disp_end * 1000)]
            samples = np.array(display_audio.get_array_of_samples())
            if display_audio.channels == 2:
                samples = samples.reshape((-1, 2)).mean(axis=1)
            factor = max(1, len(samples) // canvas_width)
            samples = samples[:factor * canvas_width].reshape((canvas_width, factor)).mean(axis=1)
            samples = samples / np.max(np.abs(samples))
            mid = canvas_height // 2
            for x, samp in enumerate(samples):
                y = int(samp * (mid - 10))
                canvas.create_line(x, mid - y, x, mid + y)

            # Tick marks every 0.5s
            for i in range(int(duration / 0.5) + 1):
                t = disp_start + i * 0.5
                x = int(((t - disp_start) / duration) * canvas_width)
                canvas.create_line(x, 0, x, canvas_height, fill='gray', dash=(2, 2))
                canvas.create_text(x + 2, canvas_height - 10, text=f"{t:.3f}", anchor='nw', font=("Arial", 6))

            # Draw markers
            def draw_markers():
                # remove previous markers and selection
                canvas.delete('marker')
                canvas.delete('selection')

                # compute pixel positions
                s_t = start_var.get()
                e_t = end_var.get()
                # clamp times to displayed range
                s_t = max(disp_start, min(s_t, disp_end))
                e_t = max(disp_start, min(e_t, disp_end))
                x_s = int(((s_t - disp_start) / duration) * canvas_width)
                x_e = int(((e_t - disp_start) / duration) * canvas_width)

                try:
                    canvas.create_rectangle(x_s, 0, x_e, canvas_height,
                                            fill='skyblue', stipple='gray25', width=0,
                                            tags=('selection',))
                except Exception:
                    canvas.create_rectangle(x_s, 0, x_e, canvas_height,
                                            fill='lightblue', width=0, tags=('selection',))

                # Draw the vertical marker lines and labels on top
                for var, tag in ((start_var, 'start_line'), (end_var, 'end_line')):
                    t = var.get()
                    # clamp
                    t = max(disp_start, min(t, disp_end))
                    x = int(((t - disp_start) / duration) * canvas_width)
                    canvas.create_line(x, 0, x, canvas_height, width=2, tag=('marker', tag))
                    canvas.create_text(x + 4, 4, text=f"{t:.3f}s", anchor='nw', tag='marker')

            draw_markers()

            # Mouse interactions
            def on_press(event):
                for tag in ('start_line', 'end_line'):
                    coords = canvas.coords(tag)
                    if coords and abs(event.x - coords[0]) < 15:
                        dragging['line'] = tag
                        break

            def on_motion(event):
                tag = dragging['line']
                if not tag: return
                x = max(0, min(event.x, canvas_width))
                t = disp_start + (x / canvas_width) * duration
                if tag == 'start_line':
                    t = min(t, end_var.get() - 0.1)
                    start_var.set(round(t, 3))
                else:
                    t = max(t, start_var.get() + 0.1)
                    end_var.set(round(t, 3))
                draw_markers()

            def on_release(event):
                dragging['line'] = None

            canvas.bind('<Button-1>', on_press)
            canvas.bind('<B1-Motion>', on_motion)
            canvas.bind('<ButtonRelease-1>', on_release)

            # Controls
            frame = tk.Frame(win)
            frame.pack(pady=5)
            tk.Label(frame, text="Start (s):").grid(row=0, column=0)
            tk.Label(frame, textvariable=start_var).grid(row=0, column=1)
            tk.Label(frame, text="End (s):").grid(row=0, column=2)
            tk.Label(frame, textvariable=end_var).grid(row=0, column=3)

            def play():
                seg = audio[int(start_var.get() * 1000):int(end_var.get() * 1000)]
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
                    path = tmp.name
                seg.export(path, format='wav')
                subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path])
                os.remove(path)

            def play_short():
                if end_var.get() - start_var.get() < 2.4:
                    play()
                    return
                second = 1000
                tick = 1
                seg = audio[int(start_var.get() * 1000):int(start_var.get() * 1000) + (tick * second)]
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
                    path = tmp.name
                seg.export(path, format='wav')
                subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path])
                os.remove(path)

                time.sleep(0.5)

                seg = audio[int(end_var.get() * 1000) - (tick * second):int(end_var.get() * 1000)]
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
                    path = tmp.name
                seg.export(path, format='wav')
                subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path])
                os.remove(path)

            def play_last(sec_bonus):
                second = 1000
                start = max(int(end_var.get() * 1000) - second, int(start_var.get() * 1000))
                seg = audio[start : int(end_var.get() * 1000) + (sec_bonus * 1000)]
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
                    path = tmp.name
                seg.export(path, format='wav')
                subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path])
                os.remove(path)

            def save_and_close():
                item["start"] = round(start_var.get(), 3)
                item["end"] = round(end_var.get(), 3)
                if txt.get("1.0", "end-1c") != item[TEXT_SEG]:
                    if messagebox.askyesno("Unsaved Text", "You Modified the Text, Wanna save it?"):
                        save_edited_text()
                nonlocal last_time
                nonlocal last_edited_id
                last_edited_id = item["id"]
                last_time = item["end"]
                done[0] = True
                nonlocal ind_el
                ind_el += 1
                win.destroy()

            def leave():
                write_the_data_in_subtitle_json(name, data)
                win.destroy()
                nonlocal last_edited_id
                print(f"last_edited_id: {last_edited_id}")
                exit(0)

            def extend_end_by_2_sec():
                new_end = min(end_var.get() + 2.0, disp_end)
                nonlocal segment_end
                segment_end = round(new_end, 3)
                win.destroy()
                launch_gui()
            
            def mark_skipped():
                if not messagebox.askyesno("Mark SKIPPED", "Mark this segment as SKIPPED-- ?"):
                    return
                if not messagebox.askyesno("Confirm", "Are you really really really SURE?"):
                    return
                item["text"] = "SKIPPED-- " + item["text"].replace("SKIPPED-- ", "")
                print("Done")
                nonlocal last_time
                nonlocal last_edited_id
                dek_time    = last_time
                dek_last_id = last_edited_id
                save_and_close()
                last_edited_id = dek_last_id
                last_time      = dek_time
            
            def back():
                done[0] = True
                nonlocal ind_el
                nonlocal last_time
                ind_el -= 1
                while str(data["segments"][ind_el]["text"]).startswith("SKIPPED-- "):
                    ind_el -= 1
                last_time = -1
                win.destroy()

            def move_marker(marker_id, amount):
                if marker_id == 1:
                    new = start_var.get() + amount
                    new = max(disp_start, min(new, end_var.get() - 0.1))
                    start_var.set(round(new, 3))
                else:
                    new = end_var.get() + amount
                    new = min(disp_end, max(new, start_var.get() + 0.1))
                    end_var.set(round(new, 3))
                draw_markers()

            def save_edited_text():
                item["text"] = txt.get("1.0", "end-1c")

            frame_butt_up = tk.Frame(win)
            frame_butt_up.pack(side="top")
            frame_butt_down = tk.Frame(win)
            frame_butt_down.pack(side="bottom")
            frame_sec_row = tk.Frame(win)
            frame_sec_row.pack(side="top")

            tk.Button(frame_butt_up, text="-0.01_s", command=lambda: move_marker(1, -0.01)).pack(pady=2, side='left')
            tk.Button(frame_butt_up, text="+0.01_s", command=lambda: move_marker(1, 0.01)).pack(pady=2, side='left')
            tk.Button(frame_butt_up, text="Play", command=play).pack(pady=2, side='left')
            tk.Button(frame_butt_up, text="-0.01_e", command=lambda: move_marker(2, -0.01)).pack(pady=2, side='left')
            tk.Button(frame_butt_up, text="+0.01_e", command=lambda: move_marker(2, 0.01)).pack(pady=2, side='left')

            tk.Button(frame_sec_row, text="Play_last 1", command=lambda: play_last(0)).pack(pady=2, side='left')
            tk.Button(frame_sec_row, text="Play SHORT", command=play_short).pack(pady=2, side='left')
            tk.Button(frame_sec_row, text="Play_last 1.1", command=lambda: play_last(0.1)).pack(pady=2, side='left')

            tk.Button(win, text="Save and Next", command=save_and_close).pack(pady=2)
            tk.Button(win, text="+2 sec", command=extend_end_by_2_sec).pack(pady=2)

            tk.Button(frame_butt_down, text="Leave Editing Mode", fg="red", command=leave).pack(pady=2, side='right')
            tk.Button(frame_butt_down, text="Mark SKIPPED", fg="red", command=mark_skipped).pack(pady=2, side='right')
            tk.Button(frame_butt_down, text="Back", command=back).pack(pady=2, side='left')

            text_frame = tk.Frame(win)
            text_frame.pack(side="bottom")
            txt = tk.Text(text_frame, height=8, width=80, wrap="word")
            txt.pack()
            txt.insert(tk.END, text_var.get())

            tk.Button(text_frame, text="Save Text", command=save_edited_text, fg="green").pack(padx=5)
            win.mainloop()

        launch_gui()
        if not done[0]:
            break

    write_the_data_in_subtitle_json(name, data)

if __name__ == "__main__":
    brain()
