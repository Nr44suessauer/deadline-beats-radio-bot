// Fetches the agent key from the static data and prints ONLY it
// (intended for redirecting into the workstation's /tmp/.botkey file).
const s = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const db = new s.Database("/home/node/.n8n/database.sqlite", s.OPEN_READONLY);

db.all("select name, staticData from workflow_entity", (error, lines) => {
  if (error) {
    console.error(error.message);
    process.exit(1);
  }
  let found = 0;
  for (const z of lines) {
    if (typeof z.staticData !== "string" || z.staticData.indexOf("testSchluessel") < 0) continue;
    let data = {};
    try {
      data = JSON.parse(z.staticData);
    } catch (reason) {
      continue;
    }
    const ganz = data.global || data;
    if (ganz && ganz.testSchluessel) {
      // Print only the agent - other workflows carry the same static data.
      if (String(z.name).indexOf("Agent") >= 0) {
        process.stdout.write(String(ganz.testSchluessel) + "\n");
        found += 1;
      }
    }
  }
  if (found === 0) console.error("No test key found in the static data.");
  db.close();
});
