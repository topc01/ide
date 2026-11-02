-- Enfoca la pestaña de Chrome que ya tiene el IDE abierto y la lleva a `target` (solo cambia el #: no
-- recarga). Si no hay ninguna, devuelve "none" (quien lo llama abre una pestaña nueva).
on run argv
	set target to item 1 of argv
	set base to item 2 of argv
	if application "Google Chrome" is not running then return "none"
	tell application "Google Chrome"
		repeat with w in windows
			set i to 0
			repeat with t in tabs of w
				set i to i + 1
				if (URL of t) starts with base then
					set URL of t to target
					set active tab index of w to i
					set index of w to 1
					activate
					return "ok"
				end if
			end repeat
		end repeat
	end tell
	return "none"
end run
