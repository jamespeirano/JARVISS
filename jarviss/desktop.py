"""Native desktop shell; all inference and storage remain in the application."""
import math
import tkinter as tk
from tkinter import ttk
from .storage import RESOURCES
from .assistant import GUIDES

BG = '#0b101b'
PANEL = '#111c2b'
TEXT = '#e4edf8'
MUTED = '#8eabc4'
ACCENT = '#65dfed'


def build(app):
    app.geometry('1280x860')
    app.minsize(1040, 760)
    rail = tk.Frame(app, bg='#080d16', width=194)
    rail.pack(side='left', fill='y')
    rail.pack_propagate(False)
    tk.Label(rail, text='◈  JARVISS', bg='#080d16', fg=TEXT,
             font=('Segoe UI', 17, 'bold')).pack(anchor='w', padx=22, pady=(30, 4))
    tk.Label(rail, text='PERSONAL • OFFLINE', bg='#080d16', fg=MUTED,
             font=('Segoe UI', 8)).pack(anchor='w', padx=24, pady=(0, 38))
    main = ttk.Frame(app, padding=(28, 20))
    main.pack(side='left', fill='both', expand=True)
    header = ttk.Frame(main)
    header.pack(fill='x', pady=(0, 18))
    app.page_title = tk.StringVar(value='Assistant')
    ttk.Label(header, textvariable=app.page_title, font=('Segoe UI', 19, 'bold')).pack(side='left')
    app.status = tk.StringVar(value='Local model not started')
    ttk.Label(header, textvariable=app.status, style='Muted.TLabel').pack(side='right')
    app.tabs = ttk.Notebook(main, style='Shell.TNotebook')
    app.tabs.pack(fill='both', expand=True)
    chat = ttk.Frame(app.tabs)
    context = ttk.Frame(app.tabs)
    app.map_tab = ttk.Frame(app.tabs)
    reference = ttk.Frame(app.tabs)
    recovery = ttk.Frame(app.tabs)
    app.setup_tab = ttk.Frame(app.tabs)
    app.nav_buttons = []
    pages = [(chat, 'Assistant'), (context, 'My situation'), (app.map_tab, 'Offline atlas'),
             (reference, 'Knowledge'), (recovery, 'Recovery plan'), (app.setup_tab, 'Settings')]
    for page, name in pages:
        app.tabs.add(page, text=name)
        button = tk.Button(rail, text=name, anchor='w', padx=20, pady=12,
                           bg='#080d16', fg=MUTED, activebackground=PANEL, activeforeground=ACCENT,
                           relief='flat', bd=0, cursor='hand2', command=lambda p=page: app.tabs.select(p))
        button.pack(fill='x', padx=10, pady=3)
        app.nav_buttons.append((page, name, button))
    def selected(_=None):
        for page, name, button in app.nav_buttons:
            active = str(page) == app.tabs.select()
            button.configure(bg=PANEL if active else '#080d16', fg=ACCENT if active else MUTED)
            if active: app.page_title.set(name)
    app.tabs.bind('<<NotebookTabChanged>>', selected)
    selected()
    tk.Label(rail, text='ON-DEVICE COMPUTE\nNo account required', justify='left',
             bg='#080d16', fg=MUTED, font=('Segoe UI', 9)).pack(side='bottom', anchor='w', padx=24, pady=28)

    hero = ttk.Frame(chat)
    hero.pack(fill='x', pady=(0, 10))
    app.orb = tk.Canvas(hero, width=150, height=128, bg=BG, highlightthickness=0)
    app.orb.pack(side='left', padx=(0, 18))
    headline = ttk.Frame(hero)
    headline.pack(side='left', fill='both', expand=True, pady=22)
    app.orb_label = tk.StringVar(value='Your local intelligence.')
    ttk.Label(headline, textvariable=app.orb_label, font=('Segoe UI', 23, 'bold')).pack(anchor='w')
    ttk.Label(headline, text='Talk through your next step. Keep your context close.',
              style='Muted.TLabel').pack(anchor='w', pady=8)
    actions = ttk.Frame(chat)
    actions.pack(fill='x', pady=(0, 12))
    for label, question in [('Plan my next step', 'What information do you need to help me plan my next step?'),
                            ('Review supplies', 'Review my saved supplies. What is missing or unclear?'),
                            ('Find water', 'Where is the nearest water?')]:
        ttk.Button(actions, text=label, command=lambda q=question: app.send(q)).pack(side='left', padx=(0, 8))
    conversation = ttk.Frame(chat)
    conversation.pack(fill='both', expand=True)
    app.transcript = app.text_box(conversation, 10)
    app.transcript.configure(font=('Segoe UI', 12), spacing1=5, spacing3=9, padx=22, pady=18)
    app.transcript.pack(side='left', fill='both', expand=True)
    scrollbar = ttk.Scrollbar(conversation, command=app.transcript.yview)
    scrollbar.pack(side='right', fill='y')
    app.transcript.configure(yscrollcommand=scrollbar.set, state='disabled')
    for tag, color in [('user', ACCENT), ('assistant', TEXT), ('system', MUTED)]:
        app.transcript.tag_configure(tag, foreground=color, spacing1=18, font=('Segoe UI', 9, 'bold'))
    app.entry = app.text_box(chat, 2)
    app.entry.pack(fill='x', pady=(12, 8))
    app.entry.bind('<Return>', app.enter_send)
    controls = ttk.Frame(chat)
    controls.pack(fill='x')
    app.voice_button = ttk.Button(controls, text='Start voice mode', command=app.toggle_voice)
    app.voice_button.pack(side='left')
    app.voice_status = tk.StringVar(value='Voice off')
    ttk.Label(controls, textvariable=app.voice_status, style='Muted.TLabel').pack(side='left', padx=12)
    app.send_button = ttk.Button(controls, text='Send  ↗', style='Accent.TButton', command=app.send)
    app.send_button.pack(side='right')
    ttk.Button(controls, text='Clear chat', command=app.clear_chat).pack(side='right', padx=8)
    app.bind('<Control-Return>', lambda _: app.send())

    app.label(context, 'Your situation', font=('Segoe UI', 18, 'bold'))
    app.label(context, 'Location, immediate priorities, and what has changed.', muted=True)
    app.situation = app.text_box(context, 5)
    app.situation.pack(fill='both', expand=True, pady=(0, 12))
    app.situation.insert('1.0', app.profile.get('situation', ''))
    app.label(context, 'People, needs & supplies', font=('Segoe UI', 16, 'bold'))
    app.supplies = app.text_box(context, 6)
    app.supplies.pack(fill='both', expand=True)
    app.supplies.insert('1.0', app.profile.get('supplies', ''))
    row = ttk.Frame(context); row.pack(fill='x', pady=16)
    app.lat = tk.StringVar(value=str(app.profile.get('lat', '')))
    app.lon = tk.StringVar(value=str(app.profile.get('lon', '')))
    for label, variable in [('Latitude', app.lat), ('Longitude', app.lon)]:
        ttk.Label(row, text=label, style='Muted.TLabel').pack(side='left', padx=(0, 10))
        ttk.Entry(row, textvariable=variable, width=15).pack(side='left', padx=(0, 20))
    ttk.Button(row, text='Save situation', style='Accent.TButton', command=app.save_profile).pack(side='right')
    app.saved = app.label(context, 'Stored on this device.', muted=True)
    app.build_map_ui()
    app.build_setup_ui()

    row = ttk.Frame(reference); row.pack(fill='x', pady=(0, 16))
    ttk.Button(row, text='Import document', style='Accent.TButton', command=app.import_reference).pack(side='left')
    app.library_status = ttk.Label(row, style='Muted.TLabel')
    app.library_status.pack(side='left', padx=16)
    app.refresh_library()
    app.label(reference, 'Local notes and manuals · TXT / Markdown', muted=True)
    box = app.text_box(reference, 20); box.pack(fill='both', expand=True)
    for note in GUIDES:
        box.insert('end', note['title']+'\n\n'+note['text']+'\n\n'+note['url']+'\n\n')
    box.configure(state='disabled')
    app.label(recovery, 'Contain. Coordinate. Rebuild.', font=('Segoe UI', 22, 'bold'))
    frame = ttk.Frame(recovery); frame.pack(fill='both', expand=True, pady=16)
    box = app.text_box(frame, 20); box.pack(side='left', fill='both', expand=True)
    scroll = ttk.Scrollbar(frame, command=box.yview); scroll.pack(side='right', fill='y')
    box.configure(yscrollcommand=scroll.set)
    document = RESOURCES / 'collective-recovery.md'
    box.tag_configure('title', font=('Segoe UI', 20, 'bold'), foreground=TEXT, spacing1=14, spacing3=12)
    box.tag_configure('heading', font=('Segoe UI', 14, 'bold'), foreground=ACCENT, spacing1=18, spacing3=10)
    box.tag_configure('body', spacing3=6)
    box.tag_configure('source', foreground=MUTED, spacing3=8)
    if document.exists():
        for line in document.read_text(encoding='utf-8').splitlines():
            tag = 'heading' if line.startswith('## ') else 'title' if line.startswith('# ') else 'source' if line.startswith('http') else 'body'
            box.insert('end', line.lstrip('# ') + '\n' if tag in ('heading', 'title') else line + '\n', tag)
    box.configure(state='disabled')
    if not app.history:
        app.append('system', 'Ready when you are. Add your situation, or start with a question.')
    animate(app, 0)


def animate(app, tick):
    # A state indicator, not simulated microphone amplitude or a network status claim.
    if not app.winfo_exists(): return
    voice = app.voice_status.get().lower()
    active = app.working or app.voice.enabled.is_set()
    label = ('Thinking locally…' if app.model_ready else 'Preparing your assistant…') if app.working else (
        'Listening to you.' if 'listening' in voice else 'Speaking.' if 'speaking' in voice else 'Your local intelligence.')
    app.orb_label.set(label)
    c = app.orb; c.delete('all')
    pulse = math.sin(tick / 5) * (3 if active else 1)
    for radius, color in [(54, '#172f46'), (44, '#24536a'), (33 + pulse, '#397f96')]:
        c.create_oval(75-radius, 64-radius, 75+radius, 64+radius, outline=color, width=2)
    angle = tick * 5 if active else 35
    c.create_arc(21, 10, 129, 118, start=angle, extent=100, style='arc', outline=ACCENT, width=3)
    c.create_arc(31, 20, 119, 108, start=-angle, extent=70, style='arc', outline='#a9beff', width=2)
    c.create_oval(68, 57, 82, 71, fill=ACCENT, outline='')
    app.after(100 if active else 240, lambda: animate(app, tick+1))
