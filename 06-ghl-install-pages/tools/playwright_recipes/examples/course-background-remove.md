# Remove one inactive template background image

Use `courses.configure_ui` with `course-background-remove.json`. Supply the exact current image URL, course and inactive template inventory. This is separate from background upload and transparency jobs.

The writer requires the current inspector URL and preview CSS image to agree, and the native Remove button to be enabled. It clicks Remove once, requires the captured native empty placeholder, disabled Remove and empty preview CSS image, preserves transparency and other preview styles, then saves and independently reopens. The active theme and sibling content must remain unchanged. Completed replay independently reopens the exact inactive template and requires the same empty inspector/preview with disabled Remove. A restored or drifted image refuses without repeating removal or changing the journal.

Only the captured Neo Classic empty state is supported. A different empty placeholder or preview structure refuses. Native empty-state capture informed this implementation; a real image-removal run, learner rendering and activation proof are not claimed. No template is activated.
