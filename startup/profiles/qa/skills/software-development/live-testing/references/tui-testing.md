# TUI App Testing

Covers terminal user interfaces built with ncurses, bubbletea, ratatui, blessed, Textual, etc.

## Launch

1. Build (see SKILL.md).
2. Launch in a pseudo-terminal so Hermes can interact with it:
   ```python
   terminal("<binary>", background=true, pty=true)
   # Wait for render, then read the screen:
   read_terminal()
   ```

The screen should show the TUI's interface — menus, prompts, or a dashboard.

## Interaction

TUIs are driven by keyboard. Use `process(action='submit')` to send keypresses, then `read_terminal()` to verify state changes:

```python
process(action='submit', data='\t')       # Tab between fields
process(action='submit', data='\r')       # Enter to select
process(action='submit', data='j')        # vim-style down
process(action='submit', data='k')        # vim-style up
process(action='submit', data='q')        # quit
process(action='submit', data='\x1b')     # Escape
process(action='submit', data='\x03')     # Ctrl+C
process(action='submit', data='hello world')  # type into a field

read_terminal()  # verify what changed
```

### Key sequences

| Key | Hex | Purpose |
|-----|-----|---------|
| Enter | `\r` or `\n` | Submit/select |
| Tab | `\t` | Next field |
| Esc | `\x1b` | Cancel/back |
| Ctrl+C | `\x03` | Interrupt |
| Ctrl+D | `\x04` | EOF |
| Ctrl+Z | `\x1a` | Suspend |
| Arrow Up | `\x1b[A` | Navigate up |
| Arrow Down | `\x1b[B` | Navigate down |
| Arrow Right | `\x1b[C` | Navigate right |
| Arrow Left | `\x1b[D` | Navigate left |
| F1-F12 | `\x1bOP` etc. | Function keys |
| Home/End | `\x1b[H` / `\x1b[F` | Line navigation |

## TUI-specific edge cases

Cases beyond the universal categories in SKILL.md:

| Category | Tests |
|----------|-------|
| Terminal resize | Resize to 80x24, then 40x10, then 200x50 — does the layout adapt? |
| Very small terminal | 20x5 — does it degrade gracefully or crash? |
| Unicode rendering | Type é, 日本語, 🎉 — rendered correctly? |
| Very long input | 1000 characters into a text field — does it overflow/truncate correctly? |
| Rapid keystrokes | Send 50 keys quickly — does the TUI keep up or garble? |
| Ctrl+C | Should exit cleanly (exit code 0 or 130) |
| Ctrl+Z | Should suspend (then `fg` to resume) |
| Terminal colors | Run with `TERM=dumb` — does it degrade without crashing? |
| Mouse events | If the TUI supports mouse, click various elements |
| Background/foreground | Launch, `Ctrl+Z` to background, `fg` — does it redraw correctly? |
| Alternative screen buffer | After exit, is the original terminal content restored? |

## Capturing TUI state

```python
screen = read_terminal()                    # current screen
read_terminal(start_line=0, count=50)       # first 50 lines of scrollback

# Send input and immediately read the result to verify state change:
process(action='submit', data='\r')
screen = read_terminal()
```

## Evidence

- Screen contents before and after each interaction (`read_terminal`)
- Exit code when the app terminates
- Text written to stderr (some TUIs log there)
- Terminal size at time of testing (for resize issues)
