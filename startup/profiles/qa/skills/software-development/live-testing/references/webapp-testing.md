# Webapp Testing

Covers SPAs (React/Vue/Svelte), SSR apps (Next/Nuxt), and traditional server-rendered webapps.

## Serve

1. Build (see SKILL.md).
2. Start the server:
   ```bash
   npm run preview -- --port 18080    # Vite preview
   npm start -- --port 18080          # Next.js
   python manage.py runserver 18080    # Django
   flask run --port 18080             # Flask
   # Or: docker compose up --build
   ```
3. Poll until ready:
   ```bash
   for i in $(seq 1 30); do curl -sf http://localhost:18080 && break; sleep 1; done
   ```

## Browser testing via Hermes tools

Use `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_vision`, `browser_console` to interact with the webapp like a real user.

### Navigate and verify the page loads
```python
browser_navigate(url="http://localhost:18080")
browser_snapshot()  # accessibility tree + interactive elements
```

### Visual check
```python
browser_vision(question="What does this page show? Are there visual errors, broken images, or layout issues?")
```

## Test patterns

### Navigation
- Click every primary navigation link — does each page load?
- `browser_back()` — does it return to the previous page?
- Direct URL navigation — does loading `/dashboard` directly work (not just via click)?

### Forms
```python
browser_type(ref="@e3", text="test@example.com")
browser_type(ref="@e5", text="password123")
browser_click(ref="@e7")  # submit button
browser_snapshot()  # verify state after submit
```

Form edge cases:
- Submit with all fields empty
- Submit with one field empty (each required field)
- Extremely long input (10000 chars)
- Special characters in all fields
- Submit the same form twice rapidly (double-submit)

### JavaScript errors
```python
# After every interaction:
browser_console()  # returns console.log/warn/error + uncaught exceptions
```

### Visual state verification
```python
browser_vision(question="After clicking 'Add to Cart', is there now a cart badge showing '1'? Are there any error messages visible?")
```

## Webapp-specific edge cases

Cases beyond the universal categories in SKILL.md:

| Category | Tests |
|----------|-------|
| Responsive | Resize browser to mobile width (375px), tablet (768px), desktop (1920px) — does layout break? |
| Console errors | Every page interaction should be console-error-free |
| Network failures | Throttle network or kill the API mid-interaction — does the UI show a graceful error? |
| Slow loading | Use a slow connection or large payload — does it show loading states? |
| Session/auth | Log in, navigate, log out, `browser_back` — is the user actually logged out? |
| Browser refresh | Fill a form, hit F5 — is the form data preserved or lost? |
| File upload | Upload a small image, a large file, an empty file, a wrong type (.exe for image field) |
| Multiple tabs | Open the app in conceptually two tabs (two browser sessions), interact in both |
| API timeout | Stop the API the webapp calls and verify the UI handles it |
| Dark mode | Toggle and check for contrast/readability issues |
| Empty states | Navigate to a view with no data — does it show an empty state or crash? |
| Deep linking | Navigate directly to a deep URL (`/users/123/edit`) — does it work without prior navigation? |

## Evidence

- Screenshots (`browser_vision`) before and after key interactions
- Console output (`browser_console`) showing any errors
- Accessibility tree snapshot showing the DOM state
- URL changes after navigation/clicks
