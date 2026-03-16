# Notes

Read, create, search, and modify Apple Notes via AppleScript.

## List Folders

```bash
osascript -e 'tell application "Notes"
    set folderList to every folder
    repeat with f in folderList
        log (name of f) & " | notes: " & (count of notes of f)
    end repeat
end tell' 2>&1
```

## List Recent Notes

```bash
osascript -e 'tell application "Notes"
    set recentNotes to notes 1 thru 10 of folder "Notes"
    repeat with n in recentNotes
        log (name of n) & " | " & (modification date of n as text)
    end repeat
end tell' 2>&1
```

## Read a Note by Name

```bash
osascript -e 'tell application "Notes"
    set n to first note whose name is "My Note Title"
    return plaintext of n
end tell'
```

## Read a Note with Metadata

```bash
osascript -e 'tell application "Notes"
    set n to first note whose name is "My Note Title"
    set noteText to plaintext of n
    set created to creation date of n as text
    set modified to modification date of n as text
    return "Created: " & created & return & "Modified: " & modified & return & return & noteText
end tell'
```

## Search Notes by Title

```bash
osascript -e 'tell application "Notes"
    set matches to every note whose name contains "search term"
    repeat with n in matches
        log (name of n) & " | " & (modification date of n as text)
    end repeat
end tell' 2>&1
```

## Search Notes by Body Content

```bash
osascript -e 'tell application "Notes"
    set matches to every note whose plaintext contains "search term"
    repeat with n in matches
        log (name of n) & " | " & (modification date of n as text)
    end repeat
end tell' 2>&1
```

## Create a Note

```bash
osascript -e 'tell application "Notes"
    make new note at folder "Notes" with properties {name:"Note Title", body:"Note content here."}
end tell'
```

Body supports HTML for formatting:
```bash
osascript -e 'tell application "Notes"
    make new note at folder "Notes" with properties {name:"Formatted Note", body:"<h1>Heading</h1><br>Paragraph text.<br><ul><li>Item 1</li><li>Item 2</li></ul>"}
end tell'
```

## Append to a Note

```bash
osascript -e 'tell application "Notes"
    set n to first note whose name is "My Note Title"
    set currentBody to body of n
    set body of n to currentBody & "<br>New line appended."
end tell'
```

## Replace a Note's Content

```bash
osascript -e 'tell application "Notes"
    set n to first note whose name is "My Note Title"
    set body of n to "<h1>My Note Title</h1><br>Replaced content."
end tell'
```

## Create a Folder

```bash
osascript -e 'tell application "Notes"
    make new folder with properties {name:"New Folder"}
end tell'
```

## Create a Note in a Specific Folder

```bash
osascript -e 'tell application "Notes"
    make new note at folder "New Folder" with properties {name:"Note Title", body:"Content"}
end tell'
```

## Delete a Note

```bash
osascript -e 'tell application "Notes"
    set n to first note whose name is "My Note Title"
    delete n
end tell'
```

Deleted notes go to "Recently Deleted" and can be recovered within 30 days.

## Notes

- Notes are returned sorted by modification date (most recent first)
- Use `plaintext` property to get clean text; use `body` to get/set HTML content
- The `name` property is the note title (first line)
- `body` accepts HTML tags: `<h1>`, `<br>`, `<b>`, `<i>`, `<ul>`, `<li>`, `<a href="">`, etc.
- Searching by `plaintext contains` checks full body content (can be slow on large collections)
- The Notes app launches silently in the background when scripted
- The default folder is "Notes" — use `folder "Notes"` to target it
- `delete` moves to Recently Deleted, not permanent deletion
- `result` is a reserved word in AppleScript — use `noteText` or other variable names instead
