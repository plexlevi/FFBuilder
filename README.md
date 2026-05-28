# FFBuilder

FFBuilder is a desktop application that brings the power of FFmpeg into a clear, easy-to-use interface.

In short: you do not have to type long command lines every time. You can work with templates, visual parameter controls, and a processing queue.

## Table Of Contents

- [What Is It Good For?](#what-is-it-good-for)
- [Who Is This For?](#who-is-this-for)
- [Typical Workflow](#typical-workflow)
- [Screenshots](#screenshots)
- [Quick Start (Developer Run)](#quick-start-developer-run)
- [Planned](#planned)

## What Is It Good For?

- Video and audio conversion with templates
- Processing multiple files in a queue
- Editing FFmpeg parameters in a visual editor
- Audio analysis (LUFS, LRA, True Peak)
- Quickly switching output formats

## Who Is This For?

- Anyone who converts media files regularly
- FFmpeg users who prefer a GUI workflow
- Users who reuse the same conversion settings often

## Typical Workflow

1. Load files
2. Choose a template (for example web, archive, audio export)
3. Set output folder and format
4. (Optional) Fine-tune options in the visual editor
5. Run the queue

## Screenshots

Screenshots and short workflow GIFs will be added soon.

## Quick Start (Developer Run)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Planned

- Installers for Windows and Linux
- More templates
- Multiple file operations