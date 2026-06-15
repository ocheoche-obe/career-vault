"""
CareerVault v1 — System Architecture Diagram Renderer
=====================================================

Renders the CareerVault v1 system architecture as PNG and PDF, using the
`diagrams` (mingrammer) library — the de-facto standard for code-driven
cloud architecture diagrams. The library ships official AWS service icons
and is widely used in production engineering teams to keep architecture
documentation version-controlled alongside the code it describes.

To regenerate the diagram after architecture changes:

    pip install diagrams --break-system-packages
    # graphviz binary must also be installed (provides the `dot` renderer):
    #   Linux:  apt install graphviz
    #   macOS:  brew install graphviz
    #   Windows: see https://graphviz.org/download/

    python render_architecture.py

Output files: careervault_architecture.png, careervault_architecture.pdf

Design conventions used (mirroring AWS official architecture diagrams):
- Top-to-bottom (TB) tier flow — request travels from user at top down
  through frontend, auth, API, compute, and data layers
- Named tier/layer clusters as siblings (not deeply nested) so graphviz
  can lay them out in a clean grid
- AWS Cloud outer boundary with official AWS-blue tint and dashed border
- Generous spacing to prevent line crossings
- Labels beneath icons (default in `diagrams`); minimal edge labels
- Solid arrows for data/request flow; dotted arrows for control-plane
"""

from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import Lambda
from diagrams.aws.database import Dynamodb
from diagrams.aws.storage import S3
from diagrams.aws.network import CloudFront, APIGateway
from diagrams.aws.security import Cognito, ACM
from diagrams.aws.integration import Eventbridge, SimpleNotificationServiceSns
from diagrams.aws.engagement import SimpleEmailServiceSes
from diagrams.aws.ml import Bedrock
from diagrams.onprem.client import Users


# === Global graph styling =====================================================

graph_attr = {
    "fontsize": "16",
    "labelloc": "t",
    "pad": "0.6",
    "nodesep": "0.6",
    "ranksep": "1.0",
    "splines": "spline",
    "bgcolor": "white",
    "compound": "true",
}

node_attr = {"fontsize": "11"}
edge_attr = {"fontsize": "10"}


# === Cluster styling ==========================================================

AWS_CLOUD_ATTR = {
    "bgcolor": "#F2F8FE",
    "pencolor": "#147EBA",
    "fontcolor": "#147EBA",
    "style": "dashed,rounded",
    "penwidth": "2",
    "fontsize": "13",
    "labeljust": "l",
    "margin": "24",
}

LAYER_ATTR = {
    "bgcolor": "#F5F5F7",
    "pencolor": "#888888",
    "fontcolor": "#444444",
    "style": "rounded",
    "penwidth": "1",
    "fontsize": "11",
    "labeljust": "l",
    "margin": "14",
}


# === Diagram ==================================================================

with Diagram(
    "CareerVault v1 — System Architecture",
    show=False,
    direction="TB",
    filename="/home/claude/careervault_architecture",
    outformat=["png", "pdf"],
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    users = Users("Users")

    with Cluster("AWS Cloud (us-east-1)", graph_attr=AWS_CLOUD_ATTR):

        # --- Top tier: Frontend + Auth ---
        with Cluster("Frontend / Presentation Layer", graph_attr=LAYER_ATTR):
            cf = CloudFront("CloudFront")
            acm = ACM("ACM Certificate")
            s3_web = S3("S3: React App\n(private, OAC)")

        with Cluster("Authentication Layer", graph_attr=LAYER_ATTR):
            cognito = Cognito("Cognito\nUser Pool")

        # --- API edge ---
        with Cluster("API Layer", graph_attr=LAYER_ATTR):
            apigw = APIGateway("API Gateway REST")

        # --- Compute ---
        with Cluster("Lambda Functions", graph_attr=LAYER_ATTR):
            chat_l = Lambda("chat_lambda")
            crud_l = Lambda("career_crud")
            resume_l = Lambda("resume_agent")
            upload_l = Lambda("resume_upload_parser")
            settings_l = Lambda("settings_lambda")
            ses_handler_l = Lambda("ses_event_handler")

        # --- Data ---
        with Cluster("Data Layer", graph_attr=LAYER_ATTR):
            ddb = Dynamodb("DynamoDB\nCareerVaultTable")
            s3_files = S3("S3: Uploads\n+ Generated PDFs")

        # --- AI ---
        with Cluster("AI Layer — Amazon Bedrock", graph_attr=LAYER_ATTR):
            claude = Bedrock("Claude\nHaiku + Sonnet")
            titan = Bedrock("Titan\nEmbeddings")

        # --- Scheduled / Background + Event Routing ---
        with Cluster("Scheduled Processing & Event Routing", graph_attr=LAYER_ATTR):
            eb = Eventbridge("EventBridge\nScheduler")
            checkin_l = Lambda("checkin_lambda")
            ses = SimpleEmailServiceSes("Amazon SES")
            sns_ses_events = SimpleNotificationServiceSns("SNS\ncareervault-ses-events")

    # === Connections ==========================================================

    # User-facing request paths
    users >> cf
    users >> cognito
    users >> apigw

    cf >> s3_web

    # Control-plane links (dotted)
    cf - Edge(style="dotted", color="gray") - acm
    apigw - Edge(style="dotted", color="gray") - cognito

    # API Gateway dispatches to handler Lambdas
    apigw >> chat_l
    apigw >> crud_l
    apigw >> resume_l
    apigw >> upload_l
    apigw >> settings_l

    # Lambda outbound dependencies
    chat_l >> ddb
    chat_l >> claude
    crud_l >> ddb
    crud_l >> titan
    resume_l >> ddb
    resume_l >> claude
    resume_l >> s3_files
    upload_l >> s3_files
    upload_l >> claude
    upload_l >> ddb
    settings_l >> ddb

    # Scheduled (cron) flow
    eb >> checkin_l
    checkin_l >> ddb
    checkin_l >> claude
    checkin_l >> ses

    # SES event routing (bounces, complaints)
    ses >> sns_ses_events
    sns_ses_events >> ses_handler_l
    ses_handler_l >> ddb

print("Rendered: careervault_architecture.png + careervault_architecture.pdf")
