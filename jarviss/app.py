import json
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from .storage import ROOT, RESOURCES, DATA, MODELS, read_json, write_json, model_path, portable_path
from .assets import prepare_demo, prepare_qwen, prepare_voice, prepare_runtime, find_server, VOICE_NAME
from .model import LocalModel
from .voice import Voice
from .maps import OfflineMap, download_area, coordinate, ATTRIBUTION
from .assistant import messages, map_answer, location, GUIDES
from .library import import_text

from .desktop import BG, PANEL, TEXT, MUTED, ACCENT


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('JARVISS')
        self.geometry('1180x800')
        self.minsize(900, 640)
        self.configure(bg=BG)
        self.events = queue.Queue()
        self.profile = read_json(DATA / 'profile.json', {})
        self.settings = read_json(DATA / 'settings.json', {})
        self.history = read_json(DATA / 'conversation.json', [])
        self.area = None
        self.route = None
        self.working = False
        self.preparing = False
        self.model_ready = False
        self.model = LocalModel()
        self.voice = Voice(lambda text: self.events.put(('heard', text)),
                           lambda text: self.events.put(('voice_status', text)),
                           lambda text: self.events.put(('error', text)))
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.style_ui()
        self.build_ui()
        try:
            pack = read_json(DATA / 'area.json', None)
            if pack:
                self.area = OfflineMap(pack)
        except (ValueError, KeyError, TypeError) as error:
            self.events.put(('error', f'Could not load map: {error}'))
        self.refresh_map()
        for item in self.history[-30:]:
            self.append(item['role'], item['content'])
        self.refresh_setup()
        self.after(100, self.poll)
        if self.settings.get('model') and model_path(self.settings['model']).exists() and find_server():
            self.after(300, self.start_model)

    def style_ui(self):
        self.option_add('*Font', ('Segoe UI' if __import__('sys').platform == 'win32' else 'Helvetica', 11))
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', background=BG, foreground=TEXT, borderwidth=0)
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG, foreground=TEXT)
        style.configure('Muted.TLabel', foreground=MUTED)
        style.configure('TButton', background='#1d3045', foreground=TEXT, padding=(14, 10))
        style.map('TButton', background=[('active', '#28455f')], foreground=[('disabled', '#69776d')])
        style.configure('Accent.TButton', background=ACCENT, foreground='#082630')
        style.map('Accent.TButton', background=[('active', '#9cf2fa')])
        style.configure('TEntry', fieldbackground=PANEL, foreground=TEXT, padding=8, insertcolor=TEXT)
        style.configure('TNotebook', background=BG, borderwidth=0)
        style.layout('Shell.TNotebook.Tab', [])
        style.layout('Shell.TNotebook', [('Notebook.client', {'sticky': 'nswe'})])
        style.configure('TNotebook.Tab', background=PANEL, foreground=MUTED, padding=(22, 12))
        style.map('TNotebook.Tab', background=[('selected', '#1d3045')], foreground=[('selected', TEXT)])
        style.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=30)
        style.configure('Treeview.Heading', background='#1d3045', foreground=TEXT)

    def label(self, parent, text, muted=False, **kw):
        widget = ttk.Label(parent, text=text, style='Muted.TLabel' if muted else 'TLabel', **kw)
        widget.pack(anchor='w', pady=(8, 5))
        return widget

    def text_box(self, parent, height=5):
        return tk.Text(parent, height=height, bg=PANEL, fg=TEXT, insertbackground=ACCENT, relief='flat',
                       padx=12, pady=10, wrap='word', undo=True, highlightthickness=1, highlightbackground='#23354b')

    def build_ui(self):
        from .desktop import build
        build(self)

    def build_map_ui(self):
        controls = ttk.Frame(self.map_tab)
        controls.pack(fill='x')
        self.search = tk.StringVar()
        ttk.Entry(controls, textvariable=self.search, width=30).pack(side='left')
        self.search.trace_add('write', lambda *_: self.refresh_places())
        ttk.Label(controls, text='Search names, water, food, medical…', style='Muted.TLabel').pack(side='left', padx=10)
        ttk.Button(controls, text='Import map pack', command=self.import_map).pack(side='right')
        ttk.Button(controls, text='Example: New York', command=self.example_map).pack(side='right', padx=8)
        self.map_meta = self.label(self.map_tab, 'No map downloaded.', muted=True)
        middle = ttk.Panedwindow(self.map_tab, orient='horizontal')
        middle.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(middle, bg='#101b2a', highlightthickness=0)
        middle.add(self.canvas, weight=3)
        self.canvas.bind('<Configure>', lambda _: self.draw_map())
        self.canvas.bind('<Button-1>', self.map_click)
        self.tree = ttk.Treeview(middle, columns=('kind', 'distance'), show='tree headings', selectmode='browse', height=10)
        self.tree.heading('#0', text='Recorded location'); self.tree.column('#0', width=190)
        self.tree.heading('kind', text='Type'); self.tree.column('kind', width=90)
        self.tree.heading('distance', text='Direct'); self.tree.column('distance', width=70)
        middle.add(self.tree, weight=2)
        self.tree.bind('<<TreeviewSelect>>', lambda _: self.draw_map())
        bottom = ttk.Frame(self.map_tab)
        bottom.pack(fill='x', pady=8)
        ttk.Button(bottom, text='Walking route to selection', command=self.route_selected).pack(side='left')
        ttk.Button(bottom, text='Export map pack', command=self.export_map).pack(side='left', padx=8)
        self.route_label = self.label(self.map_tab, '', muted=True, wraplength=1000)
        self.label(self.map_tab, 'Recorded locations only. Access, supplies, water quality, and road conditions are unverified.', muted=True)
        self.label(self.map_tab, ATTRIBUTION, muted=True)

    def build_setup_ui(self):
        self.readiness = self.label(self.setup_tab, '')
        self.label(self.setup_tab, 'Model')
        self.model_label = self.label(self.setup_tab, '', muted=True, wraplength=1000)
        row = ttk.Frame(self.setup_tab); row.pack(fill='x', pady=8)
        ttk.Button(row, text='Choose downloaded GGUF', command=self.choose_model).pack(side='left')
        ttk.Button(row, text='Start local model', command=self.start_model, style='Accent.TButton').pack(side='left', padx=8)
        self.gpu = tk.StringVar(value=str(self.settings.get('gpu_layers', 20)))
        ttk.Label(row, text='GPU layers (0 = CPU)').pack(side='left', padx=(18, 8))
        ttk.Entry(row, textvariable=self.gpu, width=6).pack(side='left')
        self.label(self.setup_tab, 'Prepare before going offline')
        row = ttk.Frame(self.setup_tab); row.pack(fill='x', pady=8)
        ttk.Button(row, text='Download recommended model', command=lambda: self.prepare(prepare_qwen)).pack(side='left')
        ttk.Button(row, text='Small demo · 400 MB', command=lambda: self.prepare(prepare_demo)).pack(side='left', padx=8)
        ttk.Button(row, text='Offline voice pack · 40 MB', command=lambda: self.prepare(prepare_voice)).pack(side='left')
        self.label(self.setup_tab, '27B: use a machine with at least 24–32 GB memory. Small demo tests the interface; it is not an emergency-advice model.', muted=True, wraplength=1000)
        self.label(self.setup_tab, 'Download your area')
        row = ttk.Frame(self.setup_tab); row.pack(fill='x', pady=8)
        ttk.Label(row, text='Radius (km)').pack(side='left')
        self.radius = tk.StringVar(value='2')
        ttk.Entry(row, textvariable=self.radius, width=6).pack(side='left', padx=8)
        ttk.Button(row, text='Download around saved coordinates', command=self.prepare_map).pack(side='left')
        self.label(self.setup_tab, 'Uses OpenStreetMap roads and resource records. Coordinates are sent only when you click Download.', muted=True)
        self.progress = self.label(self.setup_tab, '', muted=True, wraplength=1000)
        self.label(self.setup_tab, 'Offline chat and voice require no account or internet. The computer still needs batteries or independent power.', muted=True, wraplength=1000)

    def run_job(self, job, event):
        def work():
            try:
                self.events.put((event, job()))
            except Exception as error:
                self.events.put(('job_error', (event, str(error))))
        threading.Thread(target=work, daemon=True).start()

    def refresh_library(self):
        docs = read_json(DATA / 'library.json', [])
        self.library_status.configure(text=f'{len(docs)} local references')

    def import_reference(self):
        path = filedialog.askopenfilename(filetypes=[('Text and Markdown', '*.txt *.md')])
        if path:
            try:
                import_text(path); self.refresh_library()
            except (ValueError, UnicodeError, OSError) as error:
                messagebox.showerror('Reference', str(error))

    def save_profile(self):
        try:
            point = None
            if self.lat.get().strip() or self.lon.get().strip():
                point = coordinate(self.lat.get(), self.lon.get())
            previous_location = (self.profile.get('lat'), self.profile.get('lon'))
            self.profile = {'lat': point[0] if point else '', 'lon': point[1] if point else '',
                            'situation': self.situation.get('1.0', 'end').strip()[:2000],
                            'supplies': self.supplies.get('1.0', 'end').strip()[:2000]}
            write_json(DATA / 'profile.json', self.profile)
            self.saved.configure(text='Saved on this device.')
            if previous_location != (self.profile['lat'], self.profile['lon']):
                self.route = None
            self.refresh_map()
            return True
        except (ValueError, OSError) as error:
            messagebox.showerror('Situation', str(error)); return False

    def append(self, role, text):
        self.transcript.configure(state='normal')
        self.transcript.insert('end', {'user': 'YOU', 'assistant': 'JARVISS', 'system': 'STATUS'}.get(role, role) + '\n', role)
        self.transcript.insert('end', text + '\n\n')
        self.transcript.configure(state='disabled')
        self.transcript.see('end')

    def enter_send(self, event):
        if event.state & 1: return None
        self.send(); return 'break'

    def send(self, text=None):
        if self.working:
            return
        question = (text if text is not None else self.entry.get('1.0', 'end')).strip()[:4000]
        if not question:
            self.voice.busy.clear(); return
        if not self.save_profile():
            self.voice.busy.clear(); return
        direct = map_answer(question, self.profile, self.area)
        if not direct and not self.model_ready:
            self.append('system', 'Start a downloaded model in Setup.')
            self.tabs.select(self.setup_tab)
            self.voice.busy.clear(); return
        payload = messages(self.profile, self.history, question, self.area, self.route)
        self.entry.delete('1.0', 'end')
        self.append('user', question)
        self.history.append({'role': 'user', 'content': question})
        write_json(DATA / 'conversation.json', self.history[-100:])
        self.working = True
        self.voice.busy.set()
        self.send_button.configure(state='disabled')
        self.status.set('Thinking locally…')
        if direct:
            self.events.put(('answer', direct))
        else:
            self.run_job(lambda: (self.model.chat(payload), None), 'answer')

    def clear_chat(self):
        if self.working: return
        self.history = []
        write_json(DATA / 'conversation.json', [])
        self.transcript.configure(state='normal'); self.transcript.delete('1.0', 'end'); self.transcript.configure(state='disabled')

    def toggle_voice(self):
        if self.voice.enabled.is_set():
            self.voice.pause()
            self.voice_button.configure(text='Start voice mode')
        else:
            try:
                self.voice.start()
                self.voice_button.configure(text='Stop voice mode')
            except Exception as error:
                messagebox.showerror('Voice', str(error))

    def choose_model(self):
        if self.working: return
        path = filedialog.askopenfilename(filetypes=[('GGUF model', '*.gguf')])
        if path:
            self.settings['model'] = portable_path(path)
            write_json(DATA / 'settings.json', self.settings)
            self.refresh_setup()

    def start_model(self):
        if self.working or self.preparing: return
        try:
            layers = int(self.gpu.get())
            if not 0 <= layers <= 999: raise ValueError('GPU layers must be 0–999.')
            path = model_path(self.settings.get('model', ''))
            if not path.is_file(): raise ValueError('Choose or download a GGUF model first.')
        except ValueError as error:
            messagebox.showerror('Model', str(error)); return
        self.model_ready = False
        self.working = True
        self.voice.busy.set()
        self.status.set('Loading local model…')
        self.settings['gpu_layers'] = layers
        write_json(DATA / 'settings.json', self.settings)
        def load():
            self.model.stop()
            self.model.start(path, layers)
            return path.name
        self.run_job(load, 'model_ready')

    def prepare(self, function):
        if self.preparing or self.working: return
        self.preparing = True
        self.progress.configure(text='Preparing…')
        self.run_job(lambda: function(lambda text: self.events.put(('progress', text))), 'prepared')

    def prepare_map(self):
        if self.preparing: return
        if not self.save_profile(): return
        point = location(self.profile)
        if not point:
            messagebox.showerror('Map', 'Save your latitude and longitude first.'); return
        radius = self.radius.get()
        self.preparing = True
        self.run_job(lambda: download_area(*point, radius, lambda text: self.events.put(('progress', text))), 'map_ready')

    def import_map(self):
        if self.preparing: return
        path = filedialog.askopenfilename(filetypes=[('JARVISS map pack', '*.json')])
        if path:
            try:
                if Path(path).stat().st_size > 80 * 1024 * 1024: raise ValueError('Map pack too large.')
                pack = read_json(path, None)
                self.area = OfflineMap(pack)
                write_json(DATA / 'area.json', pack)
                self.route = None
                self.refresh_map(); self.refresh_setup()
            except (ValueError, KeyError, TypeError, OSError) as error:
                messagebox.showerror('Map', str(error))

    def export_map(self):
        if not self.area: return
        path = filedialog.asksaveasfilename(defaultextension='.json', initialfile='jarviss-area.json')
        if path: write_json(path, self.area.pack)

    def example_map(self):
        pack = read_json(RESOURCES / 'example-map.json', None)
        if pack:
            self.area = OfflineMap(pack)
            self.route = None
            self.refresh_map()
            self.route_label.configure(text='Example area only. Center: 40.7736, -73.9712. Your saved location has not changed.')

    def refresh_setup(self):
        name = Path(self.settings.get('model', '')).name or 'No model selected'
        self.model_label.configure(text=name)
        ready = (MODELS / VOICE_NAME / 'am' / 'final.mdl').exists()
        self.readiness.configure(text=f"Model: {'ready' if self.model_ready else 'not started'}    ·    Voice pack: {'ready' if ready else 'missing'}    ·    Map: {'saved' if self.area else 'missing'}")

    def refresh_map(self):
        if self.area:
            origin = 'your coordinates' if location(self.profile) else 'map center'
            self.map_meta.configure(text=f"{self.area.pack.get('label', 'Your area')} · OSM {self.area.pack.get('osm_timestamp', 'unknown')} · distances from {origin}")
        self.refresh_places()
        self.draw_map()

    def refresh_places(self):
        self.tree.delete(*self.tree.get_children())
        if not self.area: return
        point = location(self.profile) or self.area.pack['center']
        for i, place in enumerate(self.area.nearest(point, self.search.get(), 100)):
            self.tree.insert('', 'end', iid=place['id'], text=place['name'], values=(place['kind'], f"{place['distance_m']} m"))

    def draw_map(self):
        self.canvas.delete('all')
        if not self.area:
            self.canvas.create_text(180, 100, text='Download or import an area.', fill=MUTED)
            return
        width, height = max(self.canvas.winfo_width(), 100), max(self.canvas.winfo_height(), 100)
        s, w, n, e = self.area.pack['bounds']
        cos = math_cos((s+n)/2)
        scale = min((width-40)/((e-w)*cos), (height-40)/(n-s))
        midx, midy = (w+e)/2, (s+n)/2
        self.project = lambda p: (width/2+(p[1]-midx)*cos*scale, height/2-(p[0]-midy)*scale)
        for road in self.area.pack['roads']:
            # Never bridge missing nodes when rendering a partially downloaded way.
            for a, b in zip(road['nodes'], road['nodes'][1:]):
                if a in self.area.nodes and b in self.area.nodes:
                    self.canvas.create_line(*self.project(self.area.nodes[a]), *self.project(self.area.nodes[b]), fill='#41564a' if road['walkable'] else '#27372f', width=1)
        self.map_hits = []
        selected = self.tree.selection()
        for place in self.area.pack['places']:
            x, y = self.project(place['point'])
            color = '#79bfe8' if 'water' in place['kind'] else '#dda47d'
            radius = 6 if place['id'] in selected else 3
            self.canvas.create_oval(x-radius, y-radius, x+radius, y+radius, fill=color, outline='')
            self.map_hits.append((x, y, place['id']))
        if self.route and len(self.route['points']) > 1:
            coords = [v for p in self.route['points'] for v in self.project(p)]
            self.canvas.create_line(*coords, fill=ACCENT, width=3)
        point = location(self.profile)
        if point and self.area.contains(point):
            x, y = self.project(point)
            self.canvas.create_oval(x-6, y-6, x+6, y+6, fill=ACCENT, outline=TEXT, width=2)
            self.canvas.create_text(x+10, y-12, text='You', fill=TEXT, anchor='w')
        self.canvas.create_text(12, 12, text='N ↑', fill=MUTED, anchor='nw')

    def map_click(self, event):
        if not getattr(self, 'map_hits', None): return
        x, y, pid = min(self.map_hits, key=lambda p: (p[0]-event.x)**2+(p[1]-event.y)**2)
        if (x-event.x)**2+(y-event.y)**2 < 225:
            self.search.set('')
            if not self.tree.exists(pid):
                place = next(p for p in self.area.pack['places'] if p['id'] == pid)
                self.search.set(place['name'])
            if self.tree.exists(pid):
                self.tree.selection_set(pid); self.tree.see(pid)

    def route_selected(self):
        selected = self.tree.selection()
        if not self.area or not selected: return
        try:
            point = location(self.profile)
            if not point: raise ValueError('Save your coordinates first.')
            place = next(p for p in self.area.pack['places'] if p['id'] == selected[0])
            self.route = self.area.route(point, place['point'])
            self.route['destination'] = place['name']
            self.route_label.configure(text=f"{place['name']}: {self.route['distance_m']} m mapped walk. Endpoint gaps {self.route['start_gap_m']} / {self.route['end_gap_m']} m unverified. " + ' → '.join(self.route['roads'][:10]))
            self.draw_map()
        except ValueError as error:
            self.route = None; self.draw_map(); self.route_label.configure(text=str(error))

    def poll(self):
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == 'heard': self.send(value)
                elif event == 'voice_status':
                    self.voice_status.set(value)
                    if value == 'Voice off': self.voice_button.configure(text='Start voice mode')
                elif event == 'progress': self.progress.configure(text=value)
                elif event == 'answer':
                    answer, route = value
                    if route: self.route = route; self.draw_map()
                    self.history.append({'role': 'assistant', 'content': answer})
                    self.history = self.history[-100:]
                    write_json(DATA / 'conversation.json', self.history)
                    self.append('assistant', answer)
                    if self.voice.enabled.is_set(): self.voice.speak(answer)
                    self.finish()
                elif event == 'model_ready':
                    self.model_ready = True; self.finish(); self.refresh_setup()
                elif event == 'prepared':
                    self.preparing = False
                    self.settings = read_json(DATA / 'settings.json', {})
                    self.gpu.set(str(self.settings.get('gpu_layers', 20)))
                    self.progress.configure(text='Download complete.')
                    self.refresh_setup()
                elif event == 'map_ready':
                    self.area = OfflineMap(value); self.route = None
                    write_json(DATA / 'area.json', value)
                    self.preparing = False
                    self.progress.configure(text='Map saved for offline use.')
                    self.refresh_map(); self.refresh_setup()
                elif event in ('error', 'job_error'):
                    if event == 'job_error':
                        kind, value = value
                        if kind in ('prepared', 'map_ready'): self.preparing = False
                        else: self.finish()
                    self.append('system', str(value))
                    self.progress.configure(text=str(value))
                    self.status.set(str(value)[:100])
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def finish(self):
        self.working = False
        self.voice.busy.clear()
        self.send_button.configure(state='normal')
        self.status.set('Offline · local model ready' if self.model_ready else 'Local model not started')

    def close(self):
        self.voice.close()
        self.model.close()
        self.destroy()


def math_cos(degrees):
    import math
    return math.cos(math.radians(degrees))


def main():
    App().mainloop()


if __name__ == '__main__':
    main()
