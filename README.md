# Bincom Election Results (Flask + MySQL)

Pages
- `/`    Q1: result for one polling unit (LGA > Ward > Polling Unit chained dropdowns)
- `/lga` Q2: summed result of all polling units in an LGA (computed from announced_pu_results)
- `/new` Q3: store results for ALL parties for a new polling unit

## Run locally
1. Import `bincom_test.sql` into MySQL.
2. `pip install -r requirements.txt`
3. Set `DB_HOST`, `DB_USER`, `DB_PASS`, `DB_NAME` (defaults: localhost, root, empty, bincom_test)
4. `python app.py` and open http://localhost:5001

## Notes
- Joins use `polling_unit.uniqueid = announced_pu_results.polling_unit_uniqueid`.
- Q2 does not use `announced_lga_results`.
- Only LGAs in Delta State (state_id 25) are listed.
