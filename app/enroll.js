
export const config = {
  api: {
    bodyParser: false,
  },
};

export default function handler(req, res) {
  let rawData = "";

  req.on("data", (chunk) => {
    rawData += chunk.toString("latin1");
  });

  req.on("end", () => {
    const match = rawData.match(/<key>UDID<\/key>\s*<string>(.*?)<\/string>/);

    if (match) {
      const udid = match[1];

      // 🔴 CHANGE THIS to your real Vercel domain
      const FRONTEND_URL = "https://www.irraesign.store/";

      res.writeHead(301, {
        Location: `${FRONTEND_URL}?udid=${udid}`,
      });
      res.end();
    } else {
      res.status(400).send("UDID Extraction Failed");
    }
  });
}
