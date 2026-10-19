# Intake form and Excel synchronization

The user requires the **售后专员填写** form and **Excel 标准导入模板** to remain synchronized whenever either is changed.

- `lib/intake-schema.json` owns field identifiers, labels, required rules, dropdown options and compact Excel input positions. Browser form rendering, import mapping and Excel labels/options all use this schema.
- Change the schema, then run `npm run intake:sync`. The local authoring helper uses the bundled spreadsheet runtime; read the spreadsheet skill and run its edit-operation marker before authoring. `ARTIFACT_NODE_MODULES` can point to that runtime's node_modules directory.
- When the embedded browser schema was edited, use `npm run intake:sync -- --from-form`. When Excel labels, required stars or dropdown options were edited, use `npm run intake:sync -- --from-template` to promote those changes to the shared schema and then update both outputs. Retain existing business workflow constraints when changing enum options.
- Adding a field also requires assigning its Excel layout position without overwriting another field. Do not silently omit it from either entry path.
- After edits, run `npm run intake:check`, `node check.mjs` and `npm run test:intake-sync`. Build checks block publication if the web schema, generated workspace, template labels, required markers or dropdowns differ. Keep `app-fragment.html` and the full HTML export `lib/workspace.mjs` synchronized.
- Preserve the user's compact layout, unfrozen sheets, wide photo areas and existing values in the example sheet. Render affected spreadsheet areas after changes.
- Publish the updated site and its downloadable template together using the Sites skill. If updating the local delivered workbook too, copy the verified published template to the existing root workbook path.
- This synchronizes definitions and future downloadable templates. Downloaded/offline Excel files do not update automatically; imports do not create a live connection back to those files. Legacy sample business records remain session-local demonstrations. Customer profiles, stores, invites, requests, files and customer-origin work items are now persisted in D1/R2; keep those paths durable and separate from samples.

# Customer intake workflow

- The internal sidebar contains 客户工单中心 between 售后工单中心 and 售后审核中心. Public customer workspace is `/request`, scoped by a private per-customer invitation link; it must never expose other customers, internal review notes or expenses.
- Customer requests remain pending until an authorized 售后专员 or 管理员 checks the information and chooses an active reviewer. Only that handoff creates formal work items for the existing review flow.
- Profiles/stores support stable market IDs for future marketing-system synchronization; no external CRM connection is currently configured. Store search is confined to the invitation customer.
- New cloud-workflow changes must retain optimistic version checks and role validation. Do not substitute browser storage for shared requests or attachments. Run `node tests/customer-intake.mjs` when changing this flow.
