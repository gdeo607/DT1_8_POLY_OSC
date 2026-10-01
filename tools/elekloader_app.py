#!/usr/bin/env python3
"""elekloader, kept up to date: elekloader's own window, plus updates.

    python3 tools/elekloader_app.py

- One window at a time: a second launch says so and quits.
- At launch, and with the toolbar's "Check for updates" button, it asks GitHub whether digi1_mods,
  elekloader or the mods it builds (digisophie, digislicer, DigiFilter, digineighbor, digihealth) have new
  commits, and offers to update them.
- Updating runs `tools/dev.sh mods` (fetch, build every .elemod from your stock OS file, check which
  pairs combine), shows its output, and lists the new mods in the window. When elekloader or this
  launcher changed, it offers to restart into the new version.
- With ELEKTRON_DIR set (the folder holding "Digitakt 1"), each update also puts the new .elemod
  files in "Digitakt 1/0_Latest_Mods" and moves the previous ones to "Digitakt 1/4_bin/mods_<date>".
- At launch and after each update, copies of these mods installed by hand into elekloader's library
  (~/.elekloader/mods) are moved out ("Digitakt 1/4_bin/library_<date>", else ~/.elekloader/old_mods_<date>):
  the library is listed first and an old copy there, still ticked, would be built instead of the new one
  (an old digichain, for instance, leaves Digi Mono without its menu icons).

The stock OS file is the one chosen in the window (elekloader remembers it). Nothing here writes to
your unit.
"""
import filecmp
import glob
import os
import queue
import shutil
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEV = os.environ.get('DEV') or os.path.join(ROOT, 'out', 'dev')
TOOLS = os.path.join(DEV, 'tools')
ELEK = os.path.join(TOOLS, 'elekloader')
ELEMODS = os.path.join(DEV, 'elemods')
DEVSH = os.path.join(ROOT, 'tools', 'dev.sh')
ELEKLOADER_URL = 'https://github.com/irpina/elekloader'
# what `dev.sh mods` fetches, besides this repo
FETCHED = ('elekloader', 'digisophie', 'digislicer', 'digifilter', 'digineighbor', 'digihealth')

os.environ['PATH'] = os.pathsep.join(['/opt/homebrew/bin', '/usr/local/bin', os.environ.get('PATH', '')])

_lock = None


def git(path, *args, timeout=120):
    r = subprocess.run(['git', '-C', path] + list(args), capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip()


def head(path):
    return git(path, 'rev-parse', 'HEAD')[1] if os.path.isdir(os.path.join(path, '.git')) else ''


PROJECTS = [('digi1_mods', ROOT, '@{u}')] + [(n, os.path.join(TOOLS, n), 'origin/HEAD') for n in FETCHED]
URLS = {'digi1_mods': 'github.com/gdeo607/digi1_mods', 'elekloader': 'github.com/irpina/elekloader',
        'digisophie': 'github.com/soejrd/digisophie', 'digislicer': 'github.com/irpina/digislicer',
        'digifilter': 'github.com/DigiAlchemydsp/DigiFilter', 'digineighbor': 'github.com/irpina/digineighbor',
        'digihealth': 'github.com/irpina/digihealth'}


def check_updates():
    """-> (found, state): found is [(project, what)] for each one with new commits on GitHub, or not
    built yet; state is {project: {'behind': n, 'latest': '<date> <subject>', 'error': ...}}."""
    found, state = [], {}
    for name, path, upstream in PROJECTS:
        if not os.path.isdir(os.path.join(path, '.git')):
            found.append((name, 'not fetched yet'))
            state[name] = {'error': 'not fetched yet'}
            continue
        rc, _ = git(path, 'fetch', '-q', 'origin')
        if rc:
            found.append((name, 'could not reach GitHub'))
            state[name] = {'error': 'could not reach GitHub'}
            continue
        rc, n = git(path, 'rev-list', '--count', 'HEAD..' + upstream)
        _, subj = git(path, 'log', '-1', '--format=%h %cs %s', upstream)
        state[name] = {'behind': int(n) if rc == 0 and n.isdigit() else 0, 'latest': subj}
        if state[name]['behind']:
            found.append((name, '%s new commit%s, latest: %s' % (n, '' if n == '1' else 's', subj[8:68])))
    if not glob.glob(os.path.join(ELEMODS, '*.elemod')):
        found.append(('mods', 'not built yet'))
    return ([f for f in found if f[1] != 'could not reach GitHub'] or found), state


def project_of(path):
    """The project a listed .elemod is built from, or None (a file installed by hand)."""
    if os.path.dirname(os.path.abspath(path)) != os.path.abspath(ELEMODS):
        return None
    name = os.path.basename(path).split('-')[0].lower()
    if name == 'core':
        return 'elekloader'
    return name if name in FETCHED else 'digi1_mods'


def mirror(elektron):
    """The new .elemod files into Digitakt 1/0_Latest_Mods, the previous ones to 4_bin/mods_<date>.
    -> a line saying what happened, or None."""
    dt1 = next((d for d in sorted(glob.glob(os.path.join(elektron, 'Digitakt 1*'))) if os.path.isdir(d)), None)
    if not dt1:
        return None
    dst, bin_dir = os.path.join(dt1, '0_Latest_Mods'), os.path.join(dt1, '4_bin')
    new = sorted(glob.glob(os.path.join(ELEMODS, '*.elemod')) + glob.glob(os.path.join(ELEMODS, 'COMPATIBILITY.txt')))
    os.makedirs(dst, exist_ok=True)
    old = sorted(os.listdir(dst))
    if old == [os.path.basename(p) for p in new] and all(
            filecmp.cmp(p, os.path.join(dst, os.path.basename(p)), shallow=False) for p in new):
        return None
    line = 'The new mods are in %s.' % dst
    if old:
        arch = os.path.join(bin_dir, 'mods_' + time.strftime('%Y-%m-%d_%H%M'))
        os.makedirs(arch, exist_ok=True)
        for f in old:
            shutil.move(os.path.join(dst, f), os.path.join(arch, f))
        line += ' The previous ones are in %s.' % arch
    for p in new:
        shutil.copy2(p, dst)
    return line


def mod_id(path):
    """'digimono' for digimono-0.9.elemod (ids have no '-')."""
    return os.path.basename(path).split('-')[0].lower()


def prune_library(library):
    """Move the library's copies of the mods built here (any version) out of it.
    -> a line saying what happened, or None."""
    ours = {mod_id(p) for p in glob.glob(os.path.join(ELEMODS, '*.elemod'))}
    stale = [p for p in sorted(glob.glob(os.path.join(library, '*.elemod'))) if mod_id(p) in ours]
    if not stale:
        return None
    stamp = time.strftime('%Y-%m-%d_%H%M')
    dt1 = next((d for d in sorted(glob.glob(os.path.join(os.environ.get('ELEKTRON_DIR', '/nonexistent'),
                                                        'Digitakt 1*'))) if os.path.isdir(d)), None)
    arch = (os.path.join(dt1, '4_bin', 'library_' + stamp) if dt1
            else os.path.join(os.path.dirname(library), 'old_mods_' + stamp))
    os.makedirs(arch, exist_ok=True)
    for p in stale:
        shutil.move(p, os.path.join(arch, os.path.basename(p)))
    return ('Moved %d old copies installed by hand (%s) out of the library, to %s: the kept-up-to-date ones '
            'are used instead.' % (len(stale), ', '.join(os.path.basename(p) for p in stale), arch))


def single_instance():
    """True when no other window of this launcher is open (the lock lasts as long as the process)."""
    global _lock
    import fcntl
    d = os.path.join(os.path.expanduser('~'), '.elekloader')
    os.makedirs(d, exist_ok=True)
    _lock = open(os.path.join(d, 'app.lock'), 'w')
    try:
        fcntl.flock(_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def restart():
    if _lock:
        _lock.close()
    os.execv(sys.executable, [sys.executable] + sys.argv)


class Updates:
    """The update button, the status line and the update window, added to a LoaderWindow."""

    def __init__(self, lw, root):
        import tkinter as tk
        from tkinter import ttk
        from elekloader import gui
        self.lw, self.root, self.tk, self.C, self.FONT = lw, root, tk, gui.C, gui.FONT
        self.q = queue.Queue()
        self.busy = False
        C = gui.C
        # the header (ELEKLOADER, the stock firmware) has room; the toolbar does not
        head = next((w for w in root.pack_slaves() if w.winfo_class() == 'Frame'), None)
        if head is None:                         # elekloader's layout changed: a row of our own
            head = tk.Frame(root, background=C['panel'])
            head.pack(fill='x', before=root.pack_slaves()[0])
        box = tk.Frame(head, background=C['panel'])
        box.pack(side='left', padx=(24, 0))
        self.btn = ttk.Button(box, text='Check for updates', style='Flat.TButton', command=self.check)
        self.btn.pack(side='left')
        self.status = tk.Label(box, text='', font=(gui.FONT, 9), fg=C['muted'], bg=C['panel'])
        self.status.pack(side='left', padx=8)
        self.state, self.checked_at = {}, None
        self._version_tab(ttk)
        root.after(100, self._poll)

    # -- the Version tab --------------------------------------------------------------------------
    def _version_tab(self, ttk):
        """A "Version" tab after Description, Changes and Requirements: where the selected mod
        comes from, what it was built from, and whether GitHub has something newer."""
        tk, C, FONT = self.tk, self.C, self.FONT
        desc = self.lw.d_text.get('Description')
        if desc is None:
            return
        nb = self.root.nametowidget(desc.winfo_parent()).master    # Text -> its frame -> the Notebook
        f = ttk.Frame(nb, style='Panel.TFrame', padding=(0, 8))
        t = tk.Text(f, wrap='word', relief='flat', bg=C['panel'], fg=C['text'], font=(FONT, 9),
                    highlightthickness=0, padx=4, pady=4, cursor='arrow', height=8)
        for tag, opts in (('h', dict(font=(FONT, 9, 'bold'), foreground=C['accent2'], spacing1=6)),
                          ('m', dict(foreground=C['muted'])), ('ok', dict(foreground=C['ok'])),
                          ('warn', dict(foreground=C['warn'])), ('bad', dict(foreground=C['bad']))):
            t.tag_configure(tag, **opts)
        row = tk.Frame(f, background=C['panel'])
        row.pack(side='bottom', fill='x', pady=(6, 0))
        self.v_btn = ttk.Button(row, text='Check for updates', style='Flat.TButton', command=self._version_button)
        self.v_btn.pack(side='left')
        t.pack(fill='both', expand=True)
        t.configure(state='disabled')
        nb.add(f, text='Version')
        self.lw.d_text['Version'] = t
        shown = self.lw.show_details

        def show_details(*a, **k):
            shown(*a, **k)
            self.show_version()
        self.lw.show_details = show_details
        self.lw.tree.bind('<<TreeviewSelect>>', lambda e: self.show_version(), add='+')

    def show_version(self):
        t = self.lw.d_text.get('Version')
        sel = self.lw.tree.selection()
        if t is None or not sel:
            return
        d = self.lw.descs.get(sel[0], {})
        path = d.get('path', sel[0])
        ver = d.get('version') or '?'
        proj = project_of(path)
        if proj is None:
            newer = sorted((x.get('version', ''), q) for q, x in self.lw.descs.items()
                           if q != path and x.get('id') == d.get('id') and project_of(q))
            out = [('Installed by hand: not kept up to date\n', 'warn' if newer else 'h')]
            if newer:
                out += [('A kept-up-to-date copy is listed too (%s). Uninstall this one.\n' % newer[-1][0], 'warn')]
            out += [('\nVersion %s, in your library:\n%s\n' % (ver, path), 'm')]
            self.v_btn.configure(text='Check for updates')
            return self._write(t, out)
        src = dict((n, q) for n, q, _ in PROJECTS)[proj]
        _, built = git(src, 'log', '-1', '--format=%h %cs %s')
        st = self.state.get(proj)
        if self.busy:
            out = [('Checking GitHub...\n', 'm')]
        elif st is None:
            out = [('Not checked yet\n', 'm')]
        elif st.get('error'):
            out = [('%s\n' % st['error'].capitalize(), 'warn')]
        elif st.get('behind'):
            n = st['behind']
            out = [('Update available: %d new commit%s on GitHub\n' % (n, '' if n == 1 else 's'), 'warn'),
                   ('latest: %s\n' % st['latest'][:90], 'm')]
        else:
            out = [('Up to date\n', 'ok')]
        if self.checked_at and not self.busy:
            out += [('checked at %s\n' % self.checked_at, 'm')]
        out += [('\nVersion %s, built from %s\n' % (ver, proj), 'h'), ('%s\n' % (built[:90] or '?'), 'm'),
                ('%s\n' % URLS.get(proj, ''), 'm')]
        if ver.endswith('-chain'):
            out += [('\nChained build: ', 'h'), ('its code is %s\'s own; the SRC-page places it shares with SOPHIE, '
                     'NEIGHBOR or DIGISLICER go through digichain, which it needs (ticked with it). '
                     'That is what lets them combine.\n' % proj, 'm')]
        self.v_btn.configure(text='Update now' if st and st.get('behind') else 'Check for updates')
        self._write(t, out)

    def _write(self, t, parts):
        t.configure(state='normal')
        t.delete('1.0', 'end')
        for text, tag in parts:
            t.insert('end', text, tag)
        t.configure(state='disabled')

    def _version_button(self):
        if self.v_btn.cget('text') == 'Update now':
            self.update()
        else:
            self.check()

    def _poll(self):
        try:
            while True:
                f, a = self.q.get_nowait()
                f(*a)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _bg(self, work, done):
        def run():
            try:
                r = work()
            except Exception as e:              # a git or network failure: say so in the window
                r = e
            self.q.put((done, (r,)))
        threading.Thread(target=run, daemon=True).start()

    # -- checking ---------------------------------------------------------------------------------
    def check(self, auto=False):
        if self.busy:
            return
        self.busy = True
        self.btn.state(['disabled'])
        self.v_btn.state(['disabled'])
        self.status.configure(text='Checking...', fg=self.C['muted'])
        self.show_version()
        self._bg(check_updates, lambda r: self._checked(r, auto))

    def _checked(self, r, auto):
        from tkinter import messagebox
        self.busy = False
        self.btn.state(['!disabled'])
        self.v_btn.state(['!disabled'])
        if not isinstance(r, Exception):
            found, self.state = r
            self.checked_at = time.strftime('%H:%M')
            self.show_version()
        else:
            found = r
        if isinstance(found, Exception):
            self.status.configure(text='Could not check')
            if not auto:
                messagebox.showerror('elekloader', 'Could not check for updates:\n\n%s' % found, parent=self.root)
            return
        if all(w == 'could not reach GitHub' for _, w in found) and found:
            self.status.configure(text='Offline')
            return
        if not found:
            self.status.configure(text='Up to date', fg=self.C['ok'])
            if not auto:
                messagebox.showinfo('elekloader', 'Everything is up to date.', parent=self.root)
            return
        self.status.configure(text='Updates available', fg=self.C['accent'])
        text = '\n'.join('- %s: %s' % f for f in found)
        if messagebox.askyesno('elekloader', 'Updates available:\n\n%s\n\nUpdate now? It takes a minute or two.'
                               % text, parent=self.root):
            self.update()

    # -- updating ---------------------------------------------------------------------------------
    def update(self):
        from tkinter import messagebox
        st = self.lw.model.stock
        if not st.get('ok'):
            messagebox.showinfo('elekloader', 'Choose your stock OS file first (top right): the mods are '
                                'built from it.', parent=self.root)
            return
        tk = self.tk
        self.busy = True
        self.btn.state(['disabled'])
        self.v_btn.state(['disabled'])
        self.status.configure(text='Updating...', fg=self.C['muted'])
        self.before = (head(ROOT), head(ELEK))
        w = tk.Toplevel(self.root)
        w.title('elekloader: updating')
        w.configure(background=self.C['bg'])
        self.log = tk.Text(w, width=110, height=28, bg=self.C['panel'], fg=self.C['text'],
                           font=('Menlo', 10), relief='flat', highlightthickness=0)
        self.log.pack(fill='both', expand=True, padx=10, pady=10)
        self.logwin = w
        env = dict(os.environ, STOCK=st['path'], DEV=DEV)
        self.proc = subprocess.Popen(['bash', DEVSH, 'mods'], env=env, cwd=ROOT, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, bufsize=1)

        def pump():
            for line in self.proc.stdout:
                self.q.put((self._line, (line,)))
            self.q.put((self._updated, (self.proc.wait(),)))
        threading.Thread(target=pump, daemon=True).start()

    def _line(self, line):
        if self.log.winfo_exists():
            self.log.insert('end', line)
            self.log.see('end')

    def _updated(self, rc):
        from tkinter import messagebox
        self.busy = False
        self.btn.state(['!disabled'])
        self.v_btn.state(['!disabled'])
        if rc:
            self.status.configure(text='Update failed')
            messagebox.showerror('elekloader', 'The update failed: the window shows why (the logs are in %s).'
                                 % os.path.join(DEV, 'log'), parent=self.logwin)
            return
        note = ''
        if os.environ.get('ELEKTRON_DIR'):
            try:
                note = mirror(os.environ['ELEKTRON_DIR']) or ''
            except OSError as e:
                note = 'Could not copy the mods to your Elektron folder: %s' % e
        try:
            pruned = prune_library(self.lw.model.library)
        except OSError as e:
            pruned = 'Could not tidy the library: %s' % e
        if pruned:
            note = (note + '\n\n' + pruned).strip()
        self.lw.refresh()
        self.state = {n: dict(v, behind=0) for n, v in self.state.items() if not v.get('error')}
        self.show_version()
        self.status.configure(text='Updated', fg=self.C['ok'])
        if note:
            self._line('\n' + note + '\n')
        if (head(ROOT), head(ELEK)) != self.before:
            if messagebox.askyesno('elekloader', 'Updated. elekloader itself changed: restart it now to use '
                                   'the new version?', parent=self.logwin):
                restart()
        else:
            messagebox.showinfo('elekloader', 'Updated: the new mods are listed.%s'
                                % ('\n\n' + note if note else ''), parent=self.logwin)


def main():
    import tkinter as tk
    from tkinter import messagebox
    if not single_instance():
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo('elekloader', 'elekloader is already open.')
        return
    if not os.path.isdir(os.path.join(ELEK, '.git')):      # first launch: elekloader itself
        os.makedirs(TOOLS, exist_ok=True)
        r = subprocess.run(['git', 'clone', '-q', ELEKLOADER_URL, ELEK], capture_output=True, text=True)
        if r.returncode:
            t = tk.Tk()
            t.withdraw()
            messagebox.showerror('elekloader', 'Could not download elekloader:\n\n%s' % r.stderr)
            return
    sys.path.insert(0, ELEK)
    from elekloader import gui
    also = ([gui.BUNDLED] if os.path.isdir(gui.BUNDLED) else []) + [ELEMODS]
    os.makedirs(ELEMODS, exist_ok=True)
    try:
        pruned = prune_library(gui.LIBRARY)
    except OSError as e:
        pruned = 'Could not tidy the library: %s' % e
    root = tk.Tk()
    lw = gui.LoaderWindow(root, gui.LoaderModel(None, gui.LIBRARY, also))
    up = Updates(lw, root)
    if pruned:
        root.after(800, lambda: messagebox.showinfo('elekloader', pruned, parent=root))
    root.after(1500, lambda: up.check(auto=True))
    root.mainloop()


if __name__ == '__main__':
    main()
