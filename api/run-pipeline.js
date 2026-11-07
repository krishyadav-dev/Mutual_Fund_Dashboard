// Vercel serverless function behind the dashboard's "Sync Data" button.
//
// The pipeline can't run inside Vercel (read-only filesystem, short time
// limits, and the CSVs are baked into each deployment). Instead, this asks
// GitHub to run the "Daily Mutual Fund Data Sync" workflow. That workflow
// commits fresh CSVs to main, which makes Vercel redeploy the site.
//
// Required Vercel environment variable:
//   GH_DISPATCH_TOKEN — fine-grained GitHub token scoped to this repo
//                       with "Actions: Read and write" permission.

const REPO = process.env.GH_REPO || "krishyadav-dev/Mutual_Fund_Dashboard";
const WORKFLOW_FILE = "sync_data.yml";

module.exports = async (req, res) => {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ status: "error", message: "Use POST" });
  }

  const token = process.env.GH_DISPATCH_TOKEN;
  if (!token) {
    return res.status(500).json({
      status: "error",
      message: "GH_DISPATCH_TOKEN is not set in the Vercel project settings",
    });
  }

  try {
    const gh = await fetch(
      `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "mutual-fund-dashboard",
        },
        body: JSON.stringify({ ref: "main" }),
      }
    );

    if (gh.status === 204) {
      return res.status(202).json({
        status: "dispatched",
        message: "Data sync started on GitHub Actions",
      });
    }

    const detail = (await gh.text()).slice(0, 300);
    return res.status(502).json({
      status: "error",
      message: `GitHub API returned ${gh.status}`,
      detail,
    });
  } catch (err) {
    return res.status(502).json({ status: "error", message: String(err) });
  }
};
