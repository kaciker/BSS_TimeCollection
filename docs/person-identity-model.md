# Time Collection employee identity

`person_id` is BSS's canonical, stable employee identity. It is the Employee ID stored in `dbo.pers_person.pin` and is used to maintain one worker timeline across supported identification methods.

`reporter_id` preserves exactly what the terminal presented. For KEYPAD, it is the trimmed Employee ID entered by the employee. For RFID, it is the original canonical Reader ID, including leading zeroes. Both resolve to the same `person_id`; an RFID reporter ID is never replaced with the employee ID in BSS event history.

KEYPAD resolution queries `dbo.pers_person.pin = ?` in SECURITY_DB. It does not read `pers_attribute_ext.attr_value4` and does not run RFID candidate transformations. A person can be identified without a physical card. KEYPAD events therefore use null `credential_id` and `source_card_id`; BSS does not guess a card or create a `PersonBadgeAssignment` for keypad input. Multiple card rows do not make a PIN lookup ambiguous.

RFID continues using the established reader resolver: exact and byte-swapped `pers_attribute_ext.attr_value4` candidates are checked with the existing fail-closed ambiguity rules, and only physical RFID observations update `PersonBadgeAssignment.reader_id`.

For newly resolved events, Oracle `reporterId` is `person_id` and `reporterIdType` is `PERSON`. Local event logs continue to expose `reporter_id`, identification method, `person_id`, and credential where available. Oracle remains disabled in CORP.

Worker-state continuity, exit policy, cross-method duplicate protection, and advisory locking use `person_id` when resolved. Historical events with null `person_id` retain reporter-based fallback. Historical TimeEvents are not backfilled or rewritten.

If factory perimeter control is enabled, the resolved person's SECURITY_DB card relationship is used for read-only physical presence validation. Perimeter movements continue to represent the physical Reader ID and credential; this does not merge physical presence state with worker-state policy.
