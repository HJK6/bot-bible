# Messages

Send and read iMessages via AppleScript.

## Send a Message

```bash
osascript -e 'tell application "Messages"
    set targetService to 1st account whose service type = iMessage
    set targetBuddy to participant "+1XXXXXXXXXX" of targetService
    send "Hello from YOUR_BOT_NAME!" to targetBuddy
end tell'
```

## Send to a Contact by Name (resolve phone first)

```bash
# Step 1: Get phone number from Contacts
PHONE=$(osascript -e 'tell application "Contacts"
    set thePerson to first person whose name is "Aliyah"
    get value of first phone of thePerson
end tell')

# Step 2: Strip to digits and prepend +1
PHONE_CLEAN=$(echo "$PHONE" | tr -cd '0-9')
if [ ${#PHONE_CLEAN} -eq 10 ]; then PHONE_CLEAN="1${PHONE_CLEAN}"; fi

# Step 3: Send message
osascript -e "tell application \"Messages\"
    set targetService to 1st account whose service type = iMessage
    set targetBuddy to participant \"+${PHONE_CLEAN}\" of targetService
    send \"Hello!\" to targetBuddy
end tell"
```

## Read Recent Messages (via chat history)

```bash
osascript -e 'tell application "Messages"
    set recentChats to chats
    repeat with c in recentChats
        log (name of c) & " | " & (id of c)
    end repeat
end tell'
```

## Send to a Specific Chat by ID

```bash
osascript -e 'tell application "Messages"
    set targetChat to chat id "iMessage;-;+1XXXXXXXXXX"
    send "Hello!" to targetChat
end tell'
```

## Notes

- Phone numbers must be in E.164 format: `+1XXXXXXXXXX` (US numbers)
- The Messages app will launch in the background when scripted
- iMessage must be signed in on the Mac
- SMS relay works if iPhone is on the same Apple ID and "Text Message Forwarding" is enabled
- For contacts stored with country code already (e.g. `+1 (555) 123-4567`), strip everything except digits and `+`
- Group chats use chat IDs like `iMessage;+;chat123456`
- Sending to a new number for the first time may require the Messages app to be open
