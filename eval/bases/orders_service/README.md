# orders-service

Order placement, listing, and CSV export for the storefront.

- `app/handlers/` request handlers
- `app/clients/` outbound HTTP clients (payments, inventory)
- `app/worker.py` fulfilment queue consumer
- `config.json` defaults; override with `ORDERS_<SECTION>_<KEY>` (JSON-encoded)
