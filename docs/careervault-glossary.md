# CareerVault — Running Glossary

**Status:** Living document — grows with every session
**Last updated:** 2026-06-05

---

## How this is organized

Terms are grouped by category, then alphabetical within each. Cross-cloud parallels (Azure, GCP) are noted inline where they exist, since the goal is for CareerVault to be a stepping stone to similar projects on other cloud providers.

When a term appears in multiple categories (e.g., **SAM** is both a software engineering concept and an AWS service), it lives wherever it's most useful — usually under the AWS section.

### Categories
1. [AWS Services & Concepts](#1-aws-services--concepts)
2. [AI, ML, and Agent Concepts](#2-ai-ml-and-agent-concepts)
3. [Anthropic Products & Tools](#3-anthropic-products--tools)
4. [Software Engineering & Architecture](#4-software-engineering--architecture)
5. [Security & Networking](#5-security--networking)
6. [Frontend & Web](#6-frontend--web)

---

## 1. AWS Services & Concepts

**Amazon API Gateway**
A managed service that creates, publishes, and secures REST or HTTP APIs. Acts as the front door for client requests, routing them to backend Lambdas (or other targets) and applying auth, throttling, and rate-limiting policies. Cross-cloud: **Azure API Management**, **Google Cloud API Gateway** (or **Apigee** for the enterprise tier).

**Amazon Bedrock**
AWS's managed service for accessing foundation models (Claude, Llama, Mistral, Titan, and others) via a single SDK. You pay per token, not per server. Cross-cloud: **Azure AI Foundry** (formerly Azure OpenAI Service) for Azure-hosted models; **Vertex AI** for Gemini and other models on GCP.

**Bedrock Agents**
A managed agent-orchestration service built on top of Bedrock. You define "action groups" (Lambda functions the agent can call) and Bedrock runs the agent loop for you. The alternative is to build the loop yourself using tool use directly (see ADR-010). Cross-cloud: **Azure AI Foundry Agent Service**, **Vertex AI Agent Builder**.

**Bedrock Converse API**
A newer Bedrock interface unified across model providers. Cleaner ergonomics for tool use and multi-turn chat compared to the older `InvokeModel` API. Both APIs talk to the same underlying models; Converse is the modern way to call them. See ADR-017.

**Bedrock Knowledge Bases**
A managed RAG service: you point it at an S3 bucket of documents, it handles chunking, embedding, vector storage (typically OpenSearch Serverless under the hood, though S3 Vectors is now an option), and retrieval. Higher cost than rolling your own retrieval but turnkey. Cross-cloud equivalents: **Azure AI Search** (with Azure OpenAI), **Vertex AI Search**.

**Amazon CloudFront**
AWS's content delivery network (CDN). Caches static assets at edge locations close to users. Often used to serve the React app's built assets (see ADR-019). Cross-cloud: **Azure Front Door / Azure CDN**, **Google Cloud CDN**.

**Amazon CloudWatch**
AWS's monitoring and observability service. Logs from Lambdas land here; alarms are defined here; metrics live here. Cross-cloud: **Azure Monitor**, **Google Cloud Operations Suite (Stackdriver)**.

**Amazon Cognito**
Managed identity service. **User Pools** handle authentication (signup, login, JWT issuance). **Identity Pools** handle federated access to AWS resources. We're using a User Pool for CareerVault. Free tier covers up to 50,000 monthly active users. Cross-cloud: **Microsoft Entra ID (formerly Azure AD) External ID**, **Google Identity Platform / Firebase Auth**.

**Amazon DynamoDB**
AWS's managed NoSQL database. Single-digit-millisecond reads, on-demand or provisioned billing, scales automatically. Strong at key-value and key-range queries; weak at ad-hoc analytical queries. Cross-cloud: **Azure Cosmos DB** (specifically the Table API or Core SQL API), **Google Cloud Firestore / Bigtable**.

**DynamoDB GSI (Global Secondary Index)**
An alternate way to query a DynamoDB table using different attributes as the partition and sort key. Effectively a second copy of the table, replicated automatically as items are written to the base table. GSIs cost storage and write throughput (every write to the base table writes to every GSI). Use them when query patterns can't be satisfied by the base table's keys — but understand the cost. We opted out of GSIs at MVP per ADR-028. Cross-cloud: **Cosmos DB secondary indexes** (composite/spatial); **Firestore composite indexes**.

**DynamoDB hot partition**
DynamoDB partitions data physically by partition-key hash. A "hot partition" is one PK receiving disproportionately heavy traffic, which can trigger throttling regardless of overall table capacity. Avoided by designing PKs that distribute traffic evenly across users/tenants. Not a concern for single-user apps.

**DynamoDB item collection**
The set of all items sharing a single partition key. In single-table design, an item collection often holds all of one user's data — profile, entries, goals, conversation history — which means a single Query against `PK = USER#<user_id>` returns the full user state. Critical concept for understanding why single-table design is fast.

**Amazon EventBridge**
A serverless event bus. Lets services publish events that other services subscribe to. **EventBridge Scheduler** is a related service for cron-style scheduled jobs (this is what triggers the weekly check-in Lambda). Cross-cloud: **Azure Event Grid**, **Google Eventarc / Cloud Scheduler**.

**Amazon S3 Vectors**
A vector storage and similarity-search service for S3 buckets (launched 2025). Adds vector capabilities to standard S3 storage at a fraction of the cost of OpenSearch Serverless because it has **no always-on minimum cost** — you pay per request and per GB stored. Integrates with Bedrock Knowledge Bases as an alternative vector backend. Notable for personal-scale projects where the OpenSearch Serverless ~$172/month floor would be disqualifying. Cross-cloud: nothing exactly equivalent — Azure and GCP managed vector options (Azure AI Search, Vertex AI Vector Search) still have always-on minimum costs.

**Amazon Titan Text Embeddings**
Bedrock-hosted text embedding models. Take a string as input, return a fixed-dimension vector (1024 or 256 dimensions for the v2 model) suitable for semantic similarity search. Priced per million input tokens (~$0.02/M for Titan Embed v2), making it well-suited for embedding every record in a small/medium corpus. Cross-cloud equivalents: **Azure OpenAI text-embedding-3** family; **Vertex AI textembedding-gecko / text-embedding-005**.

**AWS Amplify**
A platform for hosting full-stack apps on AWS. Amplify Hosting deploys static sites with a Git-connected CI/CD pipeline. Amplify Libraries (frontend SDK) make it easy to talk to Cognito, AppSync, etc. We considered Amplify Hosting and rejected it in favour of S3 + CloudFront direct — see ADR-019. Cross-cloud: **Azure Static Web Apps**, **Firebase Hosting**.

**AWS Certificate Manager (ACM)**
Provisions free TLS certificates for use with AWS services (CloudFront, Load Balancers, API Gateway). Handles automatic renewal. Cross-cloud: **Azure Key Vault Certificates / App Service Managed Certs**, **Google-Managed SSL Certificates**.

**AWS Identity and Access Management (IAM)**
The core AWS authorization system. Defines who (principals) can do what (actions) on which resources. **IAM Roles** are how services authenticate to other services (Lambda's role lets it call Bedrock, etc.). The **principle of least privilege** says each role should have only the permissions it actually needs. Cross-cloud: **Microsoft Entra ID / Azure RBAC**, **Google Cloud IAM**.

**AWS IAM Identity Center**
The recommended way to manage human user access to AWS, replacing the older "IAM users with access keys" pattern. Provides single sign-on (`aws sso login` on the CLI). For machine identities (Lambdas, EC2), you still use IAM Roles.

**AWS Key Management Service (KMS)**
Managed encryption-key service. AWS services like DynamoDB and S3 use KMS keys for encryption at rest. AWS-managed keys (free) cover most needs; customer-managed keys give finer control but cost ~$1/month each. Cross-cloud: **Azure Key Vault**, **Google Cloud KMS**.

**AWS Lambda**
Serverless compute. You upload a function (Python, Node, Java, etc.); AWS runs it on demand, billing per invocation and per millisecond of execution time. No servers to manage. Cross-cloud: **Azure Functions**, **Google Cloud Functions** (or **Cloud Run** for container-based).

**Lambda layer**
A way to share code or dependencies across multiple Lambda functions. Instead of bundling the same library into every function, you create a layer and reference it. Helpful for the `aws_lambda_powertools` library and any shared utility code (e.g., our `bedrock_client.py` and Pydantic model definitions). Will also be how we package WeasyPrint's system deps (see ADR-018). Limit: 5 layers per function, 250 MB unzipped total per function.

**Amazon OpenSearch Serverless**
A managed version of OpenSearch (a fork of Elasticsearch). Used as the default vector store behind Bedrock Knowledge Bases. Strong full-text and vector search. Note: even "serverless" has a minimum cost (~$0.24/hour per OpenSearch Compute Unit, ~$172/month for 1 OCU). Cross-cloud: **Azure AI Search**, **Vertex AI Vector Search**.

**Origin Access Control (OAC)**
The modern AWS mechanism (introduced 2022) for restricting an S3 bucket so that it only serves requests coming through a specific CloudFront distribution. CloudFront signs requests to the bucket with SigV4 using its own service identity; the bucket policy grants `s3:GetObject` only to that signed-request principal from that distribution. Replaces the older **Origin Access Identity (OAI)**, which is still supported but no longer recommended. Used in CareerVault per ADR-019 to lock down the React app's S3 bucket. Cross-cloud: in Azure, **Private Endpoints** plus a Front Door routing rule serve a similar function; in GCP, signed URLs or **Cloud CDN signed cookies** with a private GCS bucket.

**Amazon S3 (Simple Storage Service)**
Object storage. Stores files (uploaded resumes, generated PDFs, static website assets). Practically infinite scale, very cheap at our volume. Cross-cloud: **Azure Blob Storage**, **Google Cloud Storage**.

**Amazon SES (Simple Email Service)**
AWS's transactional email service. Sandbox mode (default for new accounts) restricts sending to verified email addresses; production access is granted via a form. Cross-cloud: **Azure Communication Services Email**, **SendGrid** (third-party but widely used on GCP), **Mailgun**.

**Amazon Transcribe**
Server-side speech-to-text service. An alternative to using the browser's free Web Speech API for voice-mode input. Higher accuracy on long-form audio; costs ~$0.024/minute. Cross-cloud: **Azure AI Speech**, **Google Cloud Speech-to-Text**.

**AWS SAM (Serverless Application Model)**
AWS's IaC framework optimized for serverless apps. YAML-based, compiles down to CloudFormation, but adds Lambda-friendly shortcuts. Includes a local development CLI (`sam local invoke`, `sam local start-api`). Cross-cloud: **Azure Functions Core Tools** (less complete equivalent), **Google Cloud Functions Framework** (also lighter).

**AWS Secrets Manager**
Managed service for storing and rotating secrets (database passwords, API keys). More expensive than Parameter Store but adds rotation, cross-region replication. Cross-cloud: **Azure Key Vault**, **Google Secret Manager**.

**AWS Systems Manager Parameter Store**
Free (or near-free, with the Standard tier) key-value store for configuration values. Use it for non-rotating secrets and config. Cross-cloud: **Azure App Configuration**, **Google Cloud Secret Manager / Runtime Config**.

**AWS WAF (Web Application Firewall)**
A managed firewall that sits in front of CloudFront / API Gateway / ALB and blocks malicious traffic based on rules (IP allowlists, rate limits, SQL injection patterns, etc.). Cross-cloud: **Azure Web Application Firewall**, **Google Cloud Armor**.

**AWS X-Ray**
Distributed tracing service. Lets you trace a single request as it flows through multiple Lambdas / services. Integrates with `aws_lambda_powertools`. Cross-cloud: **Azure Application Insights**, **Google Cloud Trace**.

**AWS Well-Architected Framework**
AWS's official framework for evaluating cloud architecture against six pillars: Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization, and Sustainability. Worth reading at some point — it's a great mental model. Cross-cloud: **Azure Well-Architected Framework** (same five-pillar idea), **Google Cloud Architecture Framework**.

---

## 2. AI, ML, and Agent Concepts

**Agent loop**
The control flow where an LLM iteratively decides which tool to call, observes the result, and decides what to do next, until it produces a final answer. The core of any "agentic" application.

**Cosine similarity**
A measure of similarity between two vectors based on the cosine of the angle between them — i.e., it cares about *direction*, not magnitude. Defined as `(A · B) / (||A|| · ||B||)`, where the result ranges from -1 (opposite) through 0 (orthogonal) to 1 (identical direction). The standard distance metric for comparing embeddings: two pieces of text are "semantically similar" if their embedding vectors point in similar directions in vector space. Alternative metrics include dot product (cheaper but magnitude-sensitive — fine when vectors are normalized) and Euclidean distance (rarely the right choice for embeddings).

**Embedding**
A high-dimensional vector representation of text (or images, or audio). Similar inputs produce similar vectors, enabling **semantic search**: finding "the entry where I worked on a data pipeline" even if the user typed "ETL project." Bedrock provides Titan and Cohere embedding models; OpenAI has `text-embedding-3` series; Vertex has the `textembedding-gecko` family.

**Foundation Model (FM)**
A large, pre-trained model that can be adapted to many downstream tasks. Claude, GPT-4, Gemini, Llama are all foundation models. The term emphasizes that these are general-purpose starting points, not task-specific models.

**LLM (Large Language Model)**
A foundation model specifically for text/language. All the Claude family, GPT, Gemini, Llama are LLMs.

**Prompt engineering**
The practice of designing the text input (the "prompt") to get the best output from an LLM. Includes choosing instructions, examples (few-shot), structure (e.g., XML tags), and order of information.

**Prompt injection**
A class of attacks where untrusted text in a prompt manipulates the model into ignoring its real instructions. Important to think about whenever you feed user-uploaded content (resumes, job descriptions) into a model. Mitigations: clear delimiter tags, separating instructions from data, output validation.

**RAG (Retrieval-Augmented Generation)**
The pattern of retrieving relevant data from a database, vector store, or search index and injecting it into an LLM's prompt as context, improving accuracy and grounding. Critical for any system that needs to answer based on private or recent data. Has roughly two retrieval flavors: **keyword/lexical** (BM25, classic search) and **semantic/vector** (embeddings). CareerVault uses a hybrid: recency-based DynamoDB queries for check-ins, and embedding-based similarity for the resume agent (see ADR-016).

**System prompt**
The "background instructions" given to a model before the user's message. Defines persona, rules, format expectations. In Claude, sent in the `system` parameter; in OpenAI, the first `{"role": "system"}` message.

**Tool use (a.k.a. Function calling)**
The LLM API capability that lets a model request the invocation of pre-defined functions. The model responds with "I need to call `get_user_entries` with args X"; your code runs the function and feeds the result back. The mechanism behind agent loops.

**Vector search**
Searching by semantic similarity rather than exact match. The user query is embedded into a vector, and the database returns vectors closest to it (by cosine similarity or similar metric). Powered by **vector databases** like OpenSearch, Pinecone, Weaviate, or Postgres+pgvector — or, for small corpora, just by computing similarity in application code over vectors stored as attributes on regular database rows.

---

## 3. Anthropic Products & Tools

**Claude**
Anthropic's family of AI models. Current model tiers (as of mid-2026):
- **Claude Haiku** — fastest and cheapest. Good for classification, parsing, simple chat.
- **Claude Sonnet** — balanced cost/quality. The everyday workhorse.
- **Claude Opus** — most capable for complex reasoning. Most expensive.

**Claude.ai**
The consumer chat interface at claude.ai. Where you'd "talk to Claude" like ChatGPT.

**Claude API (a.k.a. Anthropic API)**
Anthropic's direct API at `api.anthropic.com`. Pay-per-token, billed by Anthropic. Always has the newest models first. Different billing relationship than calling Claude via Bedrock.

**Claude Code**
Anthropic's command-line agentic coding tool. Lives in your terminal, can read/write files, run commands, etc. Bundled with Claude Pro. This is what you'll use to actually build CareerVault.

**Claude Platform on AWS**
A newer Anthropic-direct offering hosted on AWS infrastructure. Sits between calling Bedrock (AWS-managed) and the Anthropic API directly (Anthropic-managed). Worth knowing about; not what we're using for CareerVault.

**Claude Pro**
The consumer subscription to claude.ai and Claude Code. Does NOT discount or apply to Bedrock usage — these are separately billed.

**Agent Skills**
An Anthropic feature where capabilities are packaged as folders containing a `SKILL.md` file (instructions, metadata) plus optional scripts and resources. Claude autonomously loads them when relevant. Available via the Claude API, claude.ai, Claude Code, and Claude Platform on AWS — but **not directly through Amazon Bedrock**. For CareerVault on Bedrock, we'd implement the equivalent ourselves (well-structured system prompts + tool use).

---

## 4. Software Engineering & Architecture

**Access pattern**
In NoSQL data modeling (especially DynamoDB), a specific query or write operation that the application needs to perform. The discipline of "access-pattern-first design" enumerates every query upfront and designs keys/indexes to support each one efficiently. Each pattern resolves to a single Get, Query, Put, Update, or Delete — never a Scan. CareerVault's 12 access patterns are documented in `careervault-architecture.md` section 2.2.

**ADR (Architecture Decision Record)**
A short written record of a significant architectural decision: context, decision, alternatives, consequences. The format used in `careervault-adl.md`.

**Agentic application**
A system where an LLM (or multiple LLMs) iteratively decides actions to take using tools, rather than just returning a single text response. CareerVault's resume agent is one example.

**API (Application Programming Interface)**
A contract that defines how software components interact. REST APIs are HTTP-based and conventionally JSON; GraphQL is another flavor; gRPC is the high-performance binary alternative.

**BYOK (Bring Your Own Key)**
A pattern where end users supply their own credentials/API keys to a service so the service doesn't bear the model-usage cost. Common in multi-tenant SaaS that builds on LLMs.

**DynamoDB single-table design**
Storing multiple logical entity types (users, entries, jobs, conversations) in one DynamoDB table, distinguished by composite primary keys with type prefixes (e.g., `USER#alice` / `ENTRY#01HX...`, `USER#alice` / `PROFILE`). Optimizes for cost and query efficiency by exploiting **item collections** — all items sharing the same partition key can be fetched in one Query operation. The conceptual cost is higher upfront planning; the runtime payoff is single-digit-millisecond reads at any scale. Popularized by Alex DeBrie ("The DynamoDB Book") and Rick Houlihan's AWS re:Invent talks. Cross-cloud analogs: Cosmos DB partitioning, Firestore document path design.

**Exponential backoff**
A retry strategy where the wait time between retries doubles each attempt (1s, 2s, 4s, 8s...). Prevents thundering-herd problems when a downstream service is briefly overloaded. Often paired with **jitter** (random variation) to further smooth retries.

**Functional Requirement (FR)**
A statement of what the system *does* (a feature, behavior, or capability).

**Non-Functional Requirement (NFR)**
A statement of *how well* the system does something — performance, security, reliability, cost, usability. These often map onto the AWS Well-Architected pillars.

**IaC (Infrastructure as Code)**
Defining cloud resources in version-controlled configuration files rather than clicking through a console. SAM, CDK, Terraform, Pulumi are all IaC tools.

**Idempotency**
A property of an operation where calling it multiple times has the same effect as calling it once. Important for retries — if a Lambda fails halfway, you want to be able to retry without duplicating side effects.

**Pydantic**
A Python library for runtime data validation using type hints. Define a class with typed attributes; Pydantic enforces them at instantiation. Used in CareerVault to validate API request/response bodies and DynamoDB items at the Lambda boundary, catching schema violations before they hit the database. Cross-language equivalents: **Zod** (TypeScript), **TypeBox** (TypeScript), **Joi** (older Node.js), **Marshmallow** (older Python).

**SAM template**
The YAML file that defines all AWS resources in a SAM project. Combines CloudFormation's underlying syntax with shortcuts for Lambda + API Gateway + DynamoDB.

**SRS (Software Requirements Specification)**
A formal document capturing all requirements (functional and non-functional) for a software project. The `careervault-requirements.md` file is an SRS.

**Stateless function**
A function that doesn't depend on stored data between invocations. All Lambda functions are conceptually stateless (though they can read from databases or caches). Important pattern for horizontal scalability.

**ULID (Universally Unique Lexicographically Sortable Identifier)**
A 26-character string identifier where the first 10 characters encode a millisecond-precision timestamp and the last 16 are random. Globally unique like UUIDv4 but sorts chronologically when compared alphabetically — which matters for DynamoDB sort keys, where lexicographic order is the only ordering signal. Used throughout CareerVault for entry IDs, goal IDs, session IDs, and message IDs. Modern alternative: **UUIDv7** (RFC 9562), which provides similar time-ordering. Python library: `python-ulid`.

---

## 5. Security & Networking

**Encryption at rest**
Encrypting data while it's stored on disk. DynamoDB, S3, and most managed services do this automatically using AWS-managed KMS keys.

**Encryption in transit**
Encrypting data while it moves over the network. Achieved via TLS (HTTPS). The "TLS 1.2+" requirement in NFR-4.3 covers this.

**HTTPS**
HTTP layered on top of TLS. The "S" stands for "Secure." Modern web traffic should always be HTTPS.

**JWT (JSON Web Token)**
A compact, signed token format used to convey identity and claims between services. After login, Cognito issues JWTs that the React app sends as `Authorization: Bearer <token>` headers; API Gateway validates them. Has three parts: header.payload.signature, base64-encoded.

**Least privilege (principle of)**
A foundational security idea: give each identity (user, role) only the permissions it strictly needs, no more. Applied in CareerVault by giving each Lambda its own IAM role tailored to its job.

**SSL (Secure Sockets Layer)**
The predecessor to TLS. Still casually referenced ("SSL certificate") but in practice everyone has used TLS since around 2015. Old SSL versions are insecure and should not be enabled.

**TLS (Transport Layer Security)**
The cryptographic protocol that encrypts data in transit between client and server. **TLS 1.2** (2008) is the baseline; **TLS 1.3** (2018) is current best practice. Replaces SSL.

---

## 6. Frontend & Web

**React**
A JavaScript UI library by Meta. Component-based, declarative, massive ecosystem.

**Responsive design**
Designing a UI that adapts to different screen sizes (desktop, tablet, mobile) using CSS techniques like flexbox, grid, and media queries.

**SPA routing fallback (single-page app routing)**
The pattern of configuring a static-site host to serve `index.html` for any path that doesn't match a real file, so that the client-side router (React Router, Vue Router, etc.) can handle deep-link URLs. On CloudFront, implemented via a CloudFront function or a custom error response (404 → 200 with `/index.html`). Without it, navigating directly to `/dashboard` returns a 404 instead of loading the app at the dashboard route.

**Vite**
A modern frontend build tool. Fast dev server (using native ES modules), fast production builds. Replaces older tools like webpack and Create React App in most new projects.

**Web Speech API**
A browser-native JavaScript API for speech-to-text and text-to-speech. Free, runs client-side. Quality varies by browser (Chrome uses Google's STT under the hood; Safari uses Apple's). The cheap path to voice-mode input in v1.1.
