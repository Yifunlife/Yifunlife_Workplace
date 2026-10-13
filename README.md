# YIFUN Workplace

Migration destination: Yifunlife/Yifunlife_Workplace and Cloudflare account 5a472d15dc37681abce4ab6e4eb152c3.

Run `python3 prepare_source.py` to restore the modules and migrations. Install dependencies with `pnpm install --frozen-lockfile`.

This source includes the compact two-row sales department layout. Business database and attachments are not stored in this repository.

Migration status: source prepared; deployment and business data migration pending. Existing recovery configuration must be replaced for the destination account before production deployment. Do not switch the original site until migration and access checks pass.
