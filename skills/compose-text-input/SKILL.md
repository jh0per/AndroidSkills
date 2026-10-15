---
name: compose-text-input
description: Text input in Compose beyond a plain TextField - numeric steppers that clamp instead of rejecting, TextFieldState and input transformations, keyboard options and IME actions, focus handling, and building a custom rich-text editor that applies IME edit commands (commit, composing, delete-surrounding, selection) to a multi-span model, including keyboard vendor quirks. Use when building forms with validated fields, quantity inputs, or a custom text editing surface.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - TextField
  - TextFieldState
  - InputTransformation
  - IME
  - keyboard
  - forms
  - validation
  - rich text
---

# Compose text input

## Default: Material text fields with state

Prefer `TextFieldState` + `OutlinedTextField(state = …)` (Compose Foundation 1.7+/M3 1.4+) with
`inputTransformation` for filtering and `outputTransformation` for formatting. With the value
overload, keep the field's `TextFieldValue` in the state holder for anything that must survive
recomposition or validation.

- Always a visible `label`; errors in `supportingText` with `isError = true`.
- `keyboardOptions = KeyboardOptions(keyboardType = …, imeAction = ImeAction.Next/Done, capitalization = …, autoCorrectEnabled = …)`
  and `onKeyboardAction`/`KeyboardActions` to move focus or submit.
- `Modifier.semantics { contentType = ContentType.EmailAddress }` (or autofill hints) for autofill.
- Validate on submit and on blur; do not shout errors while the person is still typing the first
  characters.

## Numeric stepper that clamps

```kotlin
private val Digits = Regex("^\\d{0,9}$")

@Composable
fun QuantityStepper(count: Int, max: Int, onChange: (Int) -> Unit, modifier: Modifier = Modifier) {
    val focus = LocalFocusManager.current
    // Re-key on count: external changes reset the field and put the cursor at the end.
    var value by remember(count) { mutableStateOf(TextFieldValue(count.toString(), TextRange(count.toString().length))) }
    Row(modifier, verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = { focus.clearFocus(); onChange((count - 1).coerceAtLeast(0)) }, enabled = count > 0) {
            Icon(Icons.Default.Remove, contentDescription = stringResource(R.string.decrease))
        }
        TextField(
            value = value,
            onValueChange = { new ->
                if (!new.text.matches(Digits)) return@TextField          // ignore non-digits, keep old value
                value = new
                onChange((new.text.toIntOrNull() ?: 0).coerceIn(0, max))  // clamp, never overflow (toIntOrNull)
            },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { focus.clearFocus() }),
            modifier = Modifier.width(72.dp),
        )
        IconButton(onClick = { focus.clearFocus(); onChange((count + 1).coerceAtMost(max)) }, enabled = count < max) {
            Icon(Icons.Default.Add, contentDescription = stringResource(R.string.increase))
        }
    }
}
```

Each icon button keeps a 48dp target and an accessible label.

## Custom rich-text editing

When text lives in your own model (several styled spans/blocks in a rich-text note), a `BasicTextField`
over a flat string loses the structure. Options, in order of preference:

1. `BasicTextField(state)` + `outputTransformation` / `AnnotatedString` styling, mapping edits back
   to spans by diffing ranges. Enough for most styled-text needs.
2. A custom input session: connect to the IME directly and apply each edit command to your model.

For option 2, the essentials:

- Convert the flat cursor/selection index into `(blockIndex, localOffset)` and back.
- Process **all** commands in a batch: one IME action can arrive as several commands (picking a
  suggestion is a delete followed by a commit).
- Commit / set-composing with no active composition: insert at the caret, advance by `text.length`.
  With an active composition: replace the composition range.
- Finish-composing: clear the composition range; if it is the first command in a batch, treat the
  composition as committed.
- Delete-surrounding: delete `before` characters before the caret within the block (merge with the
  previous block when crossing a boundary); remove empty blocks unless it is the last one.
- Ranged selection + insert: trim the tail of the start block, the head of the end block, drop
  blocks in between, insert into the start block, caret at `selection.start + text.length`.
- Ignore batches that change nothing (pure finish-composing).

Keyboard quirks to test against:

- Swipe/gesture typing sends set-composing for whole words.
- Some keyboards resend the entire composed word plus the new character instead of committing one
  character.
- Some keyboards never send delete/enter through the IME; intercept `KEYCODE_DEL` / `KEYCODE_ENTER`
  on key-down (`Modifier.onPreviewKeyEvent`) and synthesize the equivalent commands
  (finish-composing, then delete-surrounding or commit "\n").

Cover the command processor with unit tests per case (insert, composing replace, delete across
block boundary, ranged replace, emoji/surrogate pairs, RTL) and run manual checks on Gboard,
Samsung Keyboard and SwiftKey.

## Forms

- Form state (drafts, field errors, submit-in-progress) lives in the state holder; the composable
  is stateless.
- Prefer inline forms, bottom sheets or full screens over dialogs containing text fields.
- Scroll the focused field into view with IME padding (`Modifier.imePadding()` on the scroll
  container) and `BringIntoViewRequester` for multi-field forms.
- Disable the submit action while submitting and show progress on the button itself.
