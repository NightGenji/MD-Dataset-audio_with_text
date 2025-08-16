import time
import tkinter as tk
from pydub import AudioSegment
import numpy as np
import tempfile
import subprocess
import json
import os
# TODO - recommended to check the code beforehand, it is not tested
MY_DATA = "my_data/"
SUBTITLES = "subtitles.json"

WORKING_DIR_NUMBER = 2
MARGIN = 1.5       # seconds of margin around each segment
START_EDITING = 415  # from wich ID to start editing

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

def brain():
    name = get_working_folder_name(WORKING_DIR_NUMBER)
    print("Working with: " + name)
    if name is None:
        print(" <><><><><><><> Bad Working Folder Nr <><><><><><><>")
        exit(1)
    data = get_the_data_in_subtitle_json(name)

    # Load audio
    audio_path = MY_DATA + name + '/' + ".".join(name.split(".")[1:]) + ".mp3"
    audio = AudioSegment.from_mp3(audio_path)
    total_duration = audio.duration_seconds
    last_time = -1
    last_edited_id = -1

    ind_el = 0
    while ind_el < len(data["segments"]) and data["segments"][ind_el]["id"] < START_EDITING:
        ind_el += 1

    while ind_el < len(data["segments"]):
        item = data["segments"][ind_el]

        segment_start = max(item["start"], last_time)
        segment_end = item["end"]
        if segment_start > segment_end:
            item["text"] = str(item["text"]).replace("SKIPPED-- ", "")
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
            canvas_width, canvas_height = min(1900, int((duration / 0.5) * 40)), 140

            # Variables
            start_var = tk.DoubleVar(value=segment_start)
            end_var = tk.DoubleVar(value=segment_end)
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
                canvas.create_text(x + 2, canvas_height - 10, text=f"{t:.1f}", anchor='nw', font=("Arial", 6))

            # Draw markers
            def draw_markers():
                canvas.delete('marker')
                for var, tag in ((start_var, 'start_line'), (end_var, 'end_line')):
                    t = var.get()
                    x = int(((t - disp_start) / duration) * canvas_width)
                    canvas.create_line(x, 0, x, canvas_height, width=2, tag=('marker', tag))
                    canvas.create_text(x + 4, 4, text=f"{t:.2f}s", anchor='nw', tag='marker')

            draw_markers()

            # Mouse interactions
            def on_press(event):
                for tag in ('start_line', 'end_line'):
                    coords = canvas.coords(tag)
                    if coords and abs(event.x - coords[0]) < 5:
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
                if end_var.get() - start_var.get() < 3:
                    play()
                    return
                second = 1000
                seg = audio[int(start_var.get() * 1000):int(start_var.get() * 1000) + second]
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
                    path = tmp.name
                seg.export(path, format='wav')
                subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path])
                os.remove(path)

                time.sleep(0.5)

                seg = audio[int(end_var.get() * 1000) - second:int(end_var.get() * 1000)]
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
                    path = tmp.name
                seg.export(path, format='wav')
                subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path])
                os.remove(path)

            def save_and_close():
                item["start"] = round(start_var.get(), 3)
                item["end"] = round(end_var.get(), 3)
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
                val = input("Wanna mark SKIPPED-- ???? yes/no: ")
                if val == "no" or val != "yes":
                    return
                val = input("YOU SURE ???? yes/no: ")
                if val == "no" or val != "yes":
                    return
                item["text"] = "SKIPPED-- " + item["text"].replace("SKIPPED-- ", "")
                print("Done")
            
            def back():
                done[0] = True
                nonlocal ind_el
                nonlocal last_time
                ind_el -= 1
                last_time = -1
                win.destroy()

            tk.Button(win, text="Play", command=play).pack(pady=2)
            tk.Button(win, text="Play SHORT", command=play_short).pack(pady=2)
            tk.Button(win, text="Save and Next", command=save_and_close).pack(pady=2)
            tk.Button(win, text="+2 sec", command=extend_end_by_2_sec).pack(pady=2)
            tk.Button(win, text="Leave Editing Mode", fg="red", command=leave).pack(pady=2, side='right')
            tk.Button(win, text="Mark SKIPPED", fg="red", command=mark_skipped).pack(pady=2, side='right')
            tk.Button(win, text="Back", command=back).pack(pady=2, side='left')
            win.mainloop()

        launch_gui()
        if not done[0]:
            break

    write_the_data_in_subtitle_json(name, data)

if __name__ == "__main__":
    brain()
