# UuMA ChatGPT Bridge Chrome extension

This unpacked Manifest V3 extension connects an already signed-in `chatgpt.com` tab to the local
UuMA bridge on `127.0.0.1:8787`. It does not request Chrome's `cookies` permission and never reads,
copies, exports, or stores Google or ChatGPT session cookies.

## Install in the selected Chrome profile

1. Open `chrome://extensions` in that profile.
2. Enable **Developer mode**.
3. Select **Load unpacked** and choose this directory.
4. Return to the UuMA dashboard and select **Connect UuMA Chrome extension**.
5. When the account shows the connected state, select **Verify extension connection**.

The pairing token authorizes only the loopback UuMA command broker. The server stores only its
SHA-256 digest. Pairing again revokes the previous clear token.
