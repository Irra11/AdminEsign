export default function handler(req, res) {
  const rootUrl = `https://${req.headers.host}/`;
  const enrollUrl = `${rootUrl}api/enroll`;

  const profileXml = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadContent</key>
    <dict>
        <key>URL</key>
        <string>${enrollUrl}</string>
        <key>DeviceAttributes</key>
        <array>
            <string>UDID</string>
            <string>PRODUCT</string>
            <string>VERSION</string>
        </array>
    </dict>
    <key>PayloadOrganization</key>
    <string>Irra Esign Store</string>
    <key>PayloadDisplayName</key>
    <string>Get Device UDID</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
    <key>PayloadUUID</key>
    <string>${crypto.randomUUID()}</string>
    <key>PayloadIdentifier</key>
    <string>com.irra.udid</string>
    <key>PayloadType</key>
    <string>Profile Service</string>
</dict>
</plist>`;

  res.setHeader("Content-Type", "application/x-apple-aspen-config");
  res.status(200).send(profileXml);
}
