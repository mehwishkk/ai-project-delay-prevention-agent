import os
import gitlab
from google import genai
from flask import Flask, render_template, request, jsonify
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configure Gemini
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)
# Configure GitLab
gl = gitlab.Gitlab(
    "https://gitlab.com",
    private_token=os.getenv("GITLAB_TOKEN")
)

def analyze_project_delays(project_path):
    """Fetch GitLab data and analyze with Gemini"""
    
    try:
        # Connect to GitLab project
        project = gl.projects.get(project_path)
        
        # Fetch all open issues
        issues = project.issues.list(state='opened', all=True)
        
        now = datetime.now(timezone.utc)
        issue_data = []
        overdue_count = 0
        blocked_count = 0
        critical_count = 0
        
        for issue in issues:
            issue_info = {
                "id": issue.iid,
                "title": issue.title,
                "labels": issue.labels,
                "due_date": issue.due_date,
                "assignee": issue.assignee['name'] if issue.assignee else "Unassigned",
                "created_at": issue.created_at,
                "overdue": False,
                "days_overdue": 0
            }
            
            # Check if overdue
            if issue.due_date:
                due = datetime.strptime(
                    issue.due_date, "%Y-%m-%d"
                ).replace(tzinfo=timezone.utc)
                if due < now:
                    issue_info["overdue"] = True
                    issue_info["days_overdue"] = (now - due).days
                    overdue_count += 1
            
            # Count labels
            if "blocked" in [l.lower() for l in issue.labels]:
                blocked_count += 1
            if "critical" in [l.lower() for l in issue.labels]:
                critical_count += 1
                
            issue_data.append(issue_info)
        
        # Build prompt for Gemini
        prompt = f"""
You are an expert AI Project Manager. Analyze this GitLab project data 
and provide a detailed delay risk assessment.

PROJECT: {project.name}
TOTAL OPEN ISSUES: {len(issues)}
OVERDUE ISSUES: {overdue_count}
BLOCKED ISSUES: {blocked_count}  
CRITICAL ISSUES: {critical_count}

ISSUE DETAILS:
{chr(10).join([
    f"- Issue #{i['id']}: {i['title']} | "
    f"Labels: {i['labels']} | "
    f"Due: {i['due_date']} | "
    f"Assignee: {i['assignee']} | "
    f"{'OVERDUE by ' + str(i['days_overdue']) + ' days' if i['overdue'] else 'On track'}"
    for i in issue_data
])}

Please provide:
1. DELAY RISK SCORE (0-100, where 100 = certain delay)
2. TOP 3 RISK FACTORS with specific issue numbers
3. IMMEDIATE ACTIONS (specific steps to take today)
4. REASSIGNMENT SUGGESTIONS (if any assignee is overloaded)
5. EXECUTIVE SUMMARY (2-3 sentences for management)

Format your response clearly with these exact section headers.
Be specific, actionable, and reference actual issue numbers.
"""
        
        # Call Gemini
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            analysis = response.text

        except Exception:

            risk_score = min(
                100,
                overdue_count * 15 +
                blocked_count * 20 +
                critical_count * 10
            )
            top_risks = []

            for issue in issue_data[:3]:
                if issue["overdue"]:
                    status = f"{issue['days_overdue']} days overdue"
                elif "blocked" in [l.lower() for l in issue["labels"]]:
                    status = "Blocked"
                elif "critical" in [l.lower() for l in issue["labels"]]:
                    status = "Critical"
                else:
                    status = "Open"

                top_risks.append(
                    f"- Issue #{issue['id']}: {issue['title']} ({status})"
            )

            risk_list = "\n".join(top_risks)
        if risk_score >= 80:
            risk_level = "🔴 HIGH"
        elif risk_score >= 50:
            risk_level = "🟡 MEDIUM"
        else:
            risk_level = "🟢 LOW"
        analysis = f"""

🚨 DELAY RISK SCORE: {risk_score}/100
📊 RISK LEVEL: {risk_level}


TOP RISK FACTORS

{risk_list}

IMMEDIATE ACTIONS

1. Resolve overdue tasks immediately
2. Remove blockers on blocked issues
3. Review critical issues with highest priority

EXECUTIVE SUMMARY

The project is at RISK of schedule slippage due to {overdue_count} overdue tasks, {blocked_count} blocked items,
and {critical_count} critical issues requiring immediate attention.
Immediate intervention is recommended to prevent delivery delays.

Analysis generated using the AI Project Delay Prevention Engine.
"""

        # Post comment on most critical overdue issue
        comment_posted = False
        for issue_info in issue_data:
            if issue_info["overdue"] and issue_info["days_overdue"] > 5:
                try:
                    issue_obj = project.issues.get(issue_info["id"])
                    comment = f"""🤖 **AI Delay Prevention Agent Alert**

⚠️ This issue is **{issue_info['days_overdue']} days overdue** and has been flagged as a delay risk.

**Recommended Actions:**
- Update the status or due date immediately
- If blocked, add the `blocked` label and tag your team lead
- Consider reassigning if current assignee is overloaded

*This alert was automatically generated by the AI Project Delay Prevention Agent*
*Powered by AI Project Delay Prevention Agent*"""
                    
                    issue_obj.notes.create({"body": comment})
                    comment_posted = True
                    break
                except:
                    pass
        
        return {
            "success": True,
            "project": project.name,
            "total_issues": len(issues),
            "overdue_count": overdue_count,
            "blocked_count": blocked_count,
            "critical_count": critical_count,
            "analysis": analysis,
            "comment_posted": comment_posted,
            "issues": issue_data
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    project_path = data.get("project_path", "")
    
    if not project_path:
        return jsonify({"error": "No project path provided"}), 400
    
    result = analyze_project_delays(project_path)
    return jsonify(result)

@app.route("/health")
def health():
    return jsonify({"status": "ok", "agent": "AI Project Delay Prevention Agent"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

def calculate_project_risk(overdue_count, blocked_count, critical_count):
    """
    Calculate project risk score and generate executive summary.
    """

    # Risk scoring
    risk_score = (
        overdue_count * 25 +
        blocked_count * 15 +
        critical_count * 35
    )

    # Determine risk level
    if risk_score >= 70:
        risk_level = "HIGH"
    elif risk_score >= 40:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    # Generate executive summary dynamically
    if risk_level == "HIGH":
        executive_summary = (
            f"The project is at HIGH RISK of schedule slippage due to "
            f"{overdue_count} overdue task(s), "
            f"{blocked_count} blocked issue(s), and "
            f"{critical_count} critical issue(s) requiring immediate attention. "
            f"Immediate intervention is recommended to prevent delivery delays."
        )

    elif risk_level == "MEDIUM":
        executive_summary = (
            f"The project is at MODERATE RISK with "
            f"{overdue_count} overdue task(s), "
            f"{blocked_count} blocked issue(s), and "
            f"{critical_count} critical issue(s). "
            f"Proactive mitigation is recommended to maintain project timelines."
        )

    else:
        if blocked_count > 0:
            executive_summary = (
                f"The project is currently at LOW RISK. "
                f"{blocked_count} blocked issue(s) require monitoring. "
                f"The project appears to be progressing as planned."
            )
        else:
            executive_summary = (
                "The project is currently at LOW RISK with no significant "
                "schedule threats detected. The project appears to be "
                "progressing as planned."
            )

    return {
        "risk_score": min(risk_score, 100),
        "risk_level": risk_level,
        "executive_summary": executive_summary
    }

result = calculate_project_risk(
    overdue_count=0,
    blocked_count=1,
    critical_count=0
)

print(f"Risk Score: {result['risk_score']}/100")
print(f"Risk Level: {result['risk_level']}")
print(result['executive_summary'])