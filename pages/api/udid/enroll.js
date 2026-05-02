export const config = {
  api: {
    bodyParser: false, // Required to read the raw Apple plist data
  },
};

export default function handler(req, res) {
  let rawData = "";

  req.on("data", (chunk) => {
    rawData += chunk.toString("latin1");
  });

  req.on("end", () => {
    // Extract UDID using Regex
    const match = rawData.match(/<key>UDID<\/key>\s*<string>(.*?)<\/string>/);

    if (match) {
      const udid = match[1];
      const FRONTEND_URL = "https://www.irraesign.store/";

      // Redirect user back to your site with the UDID in the URL
      res.writeHead(301, {
        Location: `${FRONTEND_URL}?udid=${udid}`,
      });
      res.end();
    } else {
      res.status(400).send("UDID Extraction Failed");
    }
  });
}
