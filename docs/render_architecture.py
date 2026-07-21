"""
CareerVault v1 — System Architecture Diagram Renderer
=====================================================

Renders the CareerVault v1 system architecture as PNG and PDF using the
`diagrams` (mingrammer) library — code-driven diagrams so the picture is
version-controlled next to the architecture doc and never drifts from it.

Conventions follow the project's `render-diagram` skill
(`.claude/skills/render-diagram/`): left-to-right flow, sibling layer clusters,
orthogonal edges, external (`xlabel`) edge labels, output derived from this
file's location. See that skill for the full rationale and the graphviz
pitfalls it steers around.

To regenerate after an architecture change (same commit as the change):

    python3 -m venv .venv && .venv/bin/pip install diagrams   # once
    brew install graphviz    # provides `dot`; Linux: apt install graphviz
    .venv/bin/python docs/render_architecture.py

Output: docs/careervault_architecture.png + .pdf (basename kept stable so the
architecture doc's links don't break).
"""

from pathlib import Path

from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import Lambda
from diagrams.aws.database import Dynamodb
from diagrams.aws.storage import S3
from diagrams.aws.network import CloudFront, APIGateway
from diagrams.aws.security import Cognito
from diagrams.aws.integration import Eventbridge, SimpleNotificationServiceSns
from diagrams.aws.engagement import SimpleEmailServiceSes
from diagrams.aws.ml import Bedrock
from diagrams.onprem.client import Users


# === Global graph styling =====================================================

graph_attr = {
    "fontsize": "18",
    "labelloc": "t",
    "pad": "0.6",
    "nodesep": "0.7",
    "ranksep": "1.4",
    "splines": "ortho",   # straight right-angle edges (AWS style)
    "newrank": "true",    # global ranking across clusters — cleaner grid
    "bgcolor": "white",
}
node_attr = {"fontsize": "11"}
edge_attr = {"fontsize": "10"}


# === Cluster styling ==========================================================

AWS_CLOUD_ATTR = {
    "bgcolor": "#F2F8FE", "pencolor": "#147EBA", "fontcolor": "#147EBA",
    "style": "dashed,rounded", "penwidth": "2", "fontsize": "14",
    "labeljust": "l", "margin": "22",
}
LAYER_ATTR = {
    "bgcolor": "#FFFFFF", "pencolor": "#888888", "fontcolor": "#444444",
    "style": "rounded", "penwidth": "1", "fontsize": "11",
    "labeljust": "l", "margin": "16",
}

# Control-plane / auth / failure paths render dotted; data & request flow solid.
CTRL = {"style": "dotted", "color": "#888888"}

OUT = str(Path(__file__).resolve().parent / "careervault_architecture")


# === Diagram ==================================================================

with Diagram(
    "CareerVault v1 — System Architecture",
    show=False,
    direction="LR",
    filename=OUT,
    outformat=["png", "pdf"],
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    users = Users("User")

    with Cluster("AWS Cloud (us-east-1)", graph_attr=AWS_CLOUD_ATTR):

        # --- Interactive request path (left → right) -------------------------
        with Cluster("Frontend", graph_attr=LAYER_ATTR):
            cf = CloudFront("CloudFront\n(OAC → private S3)")
            s3_web = S3("S3: React app\n(private)")

        with Cluster("Auth", graph_attr=LAYER_ATTR):
            cognito = Cognito("Cognito\nHosted UI + JWT")

        with Cluster("API", graph_attr=LAYER_ATTR):
            apigw = APIGateway("API Gateway REST\n(JWT authorizer)")

        with Cluster("Compute — request handlers", graph_attr=LAYER_ATTR):
            chat_l = Lambda("chat_lambda")
            crud_l = Lambda("career_crud")
            resume_l = Lambda("resume_agent")
            upload_l = Lambda("resume_upload_parser")
            settings_l = Lambda("settings_lambda")

        # --- Shared backends: every handler reads/writes here ----------------
        with Cluster("Shared data & AI backends", graph_attr=LAYER_ATTR):
            ddb = Dynamodb("DynamoDB — CareerVaultTable\n(single table; all handlers read/write)")
            s3_files = S3("S3: uploads\n+ generated PDFs")
            claude = Bedrock("Bedrock — Claude\nHaiku + Sonnet")
            titan = Bedrock("Bedrock — Titan\nembeddings")

        # --- Async band: scheduled check-ins + SES event routing -------------
        with Cluster("Scheduled & event-driven", graph_attr=LAYER_ATTR):
            eb = Eventbridge("EventBridge\nScheduler")
            checkin_l = Lambda("checkin_lambda")
            ses = SimpleEmailServiceSes("Amazon SES")
            sns = SimpleNotificationServiceSns("SNS\nses-events")
            ses_handler_l = Lambda("ses_event_handler")

    # === Edges ================================================================

    # Interactive request/auth flow
    users >> cf >> s3_web
    users >> Edge(**CTRL, **{"xlabel": "login"}) >> cognito
    users >> Edge(**{"xlabel": "JWT"}) >> apigw
    apigw >> Edge(**CTRL) >> cognito          # JWT authorizer verifies the token

    # API Gateway fans out to the request handlers
    for fn in (chat_l, crud_l, resume_l, upload_l, settings_l):
        apigw >> fn

    # --- Layout pins (invisible edges; no line drawn) ------------------------
    # Stack the three entry points into one vertical column beside the user so
    # the interactive path reads left→right instead of drifting downward.
    cf - Edge(style="invis") - cognito - Edge(style="invis") - apigw
    # Seat the async band as its own row beneath the interactive one.
    apigw - Edge(style="invis") - eb

    # Handler → backend dependencies. DynamoDB is the shared datastore for all
    # handlers; to keep the star legible we draw the DDB edge only from the
    # data-owning handlers (career_crud, settings) and let the caption carry the
    # "all handlers persist here" fact. AI / S3 edges are drawn where they are
    # the defining behavior of the handler.
    crud_l >> ddb
    crud_l >> titan          # embed at write time (Titan node caption carries this)
    settings_l >> ddb
    chat_l >> claude
    resume_l >> claude
    resume_l >> s3_files
    upload_l >> claude
    upload_l >> s3_files

    # Async: scheduled check-in email
    eb >> Edge(**{"xlabel": "cron"}) >> checkin_l
    checkin_l >> claude
    checkin_l >> Edge(**{"xlabel": "send"}) >> ses

    # Async: SES bounce/complaint routing (control/failure path → dotted)
    ses >> Edge(**CTRL, **{"xlabel": "bounce"}) >> sns
    sns >> Edge(**CTRL) >> ses_handler_l
    ses_handler_l >> ddb

print("Rendered: docs/careervault_architecture.png + .pdf")
