-- Driven by app.pipelines.docs.field_regen.regenerate_fields().
-- Opens a DOCX in Microsoft Word, rebuilds every TOC from current headings,
-- saves the DOCX in place with the fresh cache, closes without prompting.
--
-- usage: osascript _regen_fields.applescript <docx_path>

on run argv
    if (count of argv) < 1 then error "usage: osascript _regen_fields.applescript <docx_path>"
    set p to item 1 of argv
    tell application "Microsoft Word"
        activate
        delay 3
        with timeout of 300 seconds
            open file name p
            repeat 100 times
                if (count of documents) > 0 then exit repeat
                delay 0.1
            end repeat
            set nTocs to count of (tables of contents of document 1)
            repeat with i from 1 to nTocs
                update (table of contents i of document 1)
            end repeat
            save document 1
            close document 1 saving no
        end timeout
    end tell
end run
