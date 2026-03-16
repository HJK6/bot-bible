# Contacts

Read macOS Contacts via AppleScript.

## List All Contacts

```bash
osascript -e 'tell application "Contacts" to get name of every person'
```

## Get a Specific Contact's Phone Number

```bash
osascript -e 'tell application "Contacts"
    set thePerson to first person whose name is "John Smith"
    get value of phones of thePerson
end tell'
```

## Get a Specific Contact's Email

```bash
osascript -e 'tell application "Contacts"
    set thePerson to first person whose name is "John Smith"
    get value of emails of thePerson
end tell'
```

## Search Contacts by Name (partial match)

```bash
osascript -e 'tell application "Contacts"
    set matches to every person whose name contains "Ali"
    repeat with p in matches
        log (name of p) & " | " & (value of phones of p as text)
    end repeat
end tell'
```

## Get Full Contact Details

```bash
osascript -e 'tell application "Contacts"
    set thePerson to first person whose name is "John Smith"
    set theName to name of thePerson
    set thePhones to value of phones of thePerson
    set theEmails to value of emails of thePerson
    return theName & " | Phones: " & (thePhones as text) & " | Emails: " & (theEmails as text)
end tell'
```

## Notes

- Contact names are case-insensitive for `contains` but case-sensitive for exact `is` match
- Phone numbers are returned as-is from the contact card (may include formatting like `(214) 457-1997`)
- For iMessage/SMS use, strip to digits and prepend `+1`: e.g. `(214) 457-1997` → `+12144571997`
- The Contacts app will launch silently in the background when queried
