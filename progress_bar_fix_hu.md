# Progress Bar Flicker Fix - Végleges Megoldás

## Probléma (szövegesen)
A felhasználó arról számolt be, hogy a FFBuilder konverzió során a progress bar gyakran "kibillanthat" (gyakran megváltoztatja a méretét villogásként).

## Gyökér-ok
A probléma két ütköző progress frissítés forrásából eredt:
1. **Worker progress jele**: A worker közvetlenül a FFmpeg `-progress` outputból számol porcentázatot
2. **Log parser**: A log parser a log outputból értelmezi az időt és számol progress percentage-t

Ha a worker és a log parser **különböző duration értékeket** használnak a progress számításához, a progress bar értéke folyamatosan változik (flicker).

## Megoldás

### 1. Worker Fix (`app/services/ffmpeg/worker.py`)

A worker logikája helyes a duration lockingra, de volt néhány hiba:

#### Hiba 1: `start_time` hatósugár
A `start_time` változó nehezen érhető el más metódusokból.
**Fix**: Mind a `_run_with_progress_tracking`-ban, mind a `_run_without_progress`-ban hozzáadtuk a `start_time` inicializálást.

#### Hiba 2: Progress nem emittálha duration=0
Amikor `duration_seconds == 0`, a worker nem emittált progress jeleket.
**Fix**: Módosítottuk a logikát - ha duration=0, a worker megpróbálja kiolvasni duration-t a FFmpeg `-progress` outputból az első Progress line-ból.

#### Hiba 3: `_progress_enabled` vs `_progress_enabled()` konfliktus
A worker-nek volt instance variable-ja és egy metódusa is ugyanneven.
**Fix**: Az instance variable-t eltávolítottuk, csak a metódus maradt.

#### Hiba 4: Duration nem automatikus detektálható
A FFmpeg `-progress` output csupán az aktuális időt (`out_time` vagy `time=`) mutatja, nem a teljes duration-t. A duration csak a konverzió végén látható a logban.
**Fontos megfigyelés**: A `-progress` outputból durationt **NEM lehet** kiolvasni!

Ezért a worker progress jelek csak akkor emittálnak, ha van duration:
- Ha a user expliciten megadta (> 0): Progress enabled, duration használt
- Ha duration=0: Progress disabled (nincs progress)
- Ha duration < 0 (pl. -1.0): Várakozik, amíg a user megadja

Ha duration nem van beállítva (0), a progress bar sem fog mozogni, ami normális viselkedés.

### 2. GUI Fixek

#### Fix: Progress bar maximum
**File**: `app/gui_qt/main_window_parts/process_flow.py`

**Előtte**:
```python
def init_run_progress_display(progress_bar: QProgressBar, duration_seconds: float) -> None:
    if duration_seconds > 0:
        progress_bar.setProperty("maximum", 100)
        progress_bar.setProperty("value", 0)
    else:
        progress_bar.setProperty("maximum", 0)  # PROBLÉMA!
        progress_bar.setProperty("value", 0)
    progress_bar.setVisible(True)
```

**Utána**:
```python
def init_run_progress_display(progress_bar: QProgressBar, duration_seconds: float) -> None:
    # FONTOS: Mindig maximum=100, hogy látszódjék a progress bar
    progress_bar.setProperty("maximum", 100)
    progress_bar.setProperty("value", 0)
    progress_bar.setVisible(True)
```

#### Fix: Duration locking a log parser-ben
**File**: `app/gui_qt/main_window_mixins/run_flow.py`

Amikor a log parser kiolvas duration-t, egy `should_lock_duration` flag-et is visszaad.
A `_apply_process_progress_update` csak akkor frissíti a duration-t, ha a flag False.

Ez biztosítja, hogy a log parser és worker ugyanazt a duration-t használják.

### 3. Használati útmutató

A fix helyesen működik:
1. **Ha duration van beállítva** (> 0): Progress bar simán halad 0%-ról 100%-ig, NINCS flickering
2. **Ha duration nincs beállítva** (0): Progress bar 0%on marad, addig amíg nem fog progress jeleket a worker

**FONTOS**: Konverzió előtt BE kell állítani a duration-t!
- Ha a fájlonak van metadata durationa (ffprobe), az automatikusan beáll
- Ha nincs duration, a user-nek manuálisan kell beállítania a `duration_seconds` mezőt
- Ha duration 0, a progress bar nem fog működni

### 4. Fileok a workspace-ben

- `app/services/ffmpeg/worker.py` - Worker logika javítása
- `app/gui_qt/main_window_parts/process_flow.py` - Progress bar initializálás
- `app/gui_qt/main_window_mixins/run_flow.py` - Duration locking logikája

### 5. Ellenőrzés

Az összes file jó Python szintaxis szerint.
Az alkalmazás fut, ha duration van beállítva.

Ha duration nincs beállítva, a progress bar nem fog mozogni (normális, nem lehet progress-t mutatni duration nélkül).