# Stock alert push notifications

SoloBiz sends a push notification to a user's devices when a sale makes a
product low on stock (at or below its "Alert at" level) or sells it out.
Users turn it on per device from the Inventory page.

## Setup (once)

1. Generate a key pair:

   ```bash
   python -m server.tools.generate_vapid_keys
   ```

2. Set these environment variables on the web service (e.g. Render):

   | Variable | Value |
   | --- | --- |
   | `VAPID_PUBLIC_KEY` | printed public key |
   | `VAPID_PRIVATE_KEY` | printed private key (keep secret) |
   | `VAPID_SUBJECT` | `mailto:` your support email, or your site URL |

3. Redeploy. The "Stock alert notifications" card appears on the Inventory
   page only when the keys are set.

Keep the same key pair afterwards: replacing it stops delivery to every
device that already turned notifications on, until each one turns them on again.

## Notes

- Notifications need HTTPS (localhost is fine for development).
- On iPhone/iPad (iOS 16.4+) they only work after adding SoloBiz to the Home
  Screen and opening it from there.
- If SoloBiz is open and in front when an alert arrives, it is shown inside
  the page instead of as a system notification.
- Signing out removes that device's subscription, so another person signing
  in on the same device does not receive the previous account's alerts.
