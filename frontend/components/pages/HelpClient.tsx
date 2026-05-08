"use client";
import { useState } from "react";
import { bugReportMailto, supportEmail, supportMailto } from "@/lib/site";

interface Section {
	id: string;
	title: string;
	content: React.ReactNode;
}

export default function HelpClient() {
	const [openSections, setOpenSections] = useState<Set<string>>(new Set(["getting-started"]));
	const supportText = supportEmail;

	const toggleSection = (id: string) => {
		setOpenSections((prev) => {
			const next = new Set(prev);
			if (next.has(id)) {
				next.delete(id);
			} else {
				next.add(id);
			}
			return next;
		});
	};

	const expandAll = () => {
		setOpenSections(new Set(sections.map((s) => s.id)));
	};

	const collapseAll = () => {
		setOpenSections(new Set());
	};

	const sections: Section[] = [
		{
			id: "getting-started",
			title: "Getting Started",
			content: (
				<div className="space-y-4">
					<div>
						<h3 className="font-semibold text-lg mb-2">What is Restailor?</h3>
						<p className="text-slate-300">
							Restailor is a free, open-source resume tailoring tool that helps you customize your resume for any job application.
							It is hosted for people to use and enjoy, while model runs use your own AI provider API key.
						</p>
					</div>

					<div className="bg-amber-900/20 border border-amber-700/50 rounded-lg p-4">
						<h3 className="font-semibold text-lg mb-3 text-amber-200">Free BYOK Model</h3>
						<ul className="space-y-2 text-slate-300">
							<li className="flex items-start gap-2">
								<span className="text-green-400 mt-1">-</span>
								<span><strong>Free to use:</strong> Restailor does not charge you for access.</span>
							</li>
							<li className="flex items-start gap-2">
								<span className="text-green-400 mt-1">-</span>
								<span><strong>Bring your own key:</strong> Add your provider API key in Settings before running models.</span>
							</li>
							<li className="flex items-start gap-2">
								<span className="text-green-400 mt-1">-</span>
								<span><strong>No markup:</strong> Provider prices are shown for planning; Restailor does not add a fee.</span>
							</li>
							<li className="flex items-start gap-2">
								<span className="text-green-400 mt-1">-</span>
								<span><strong>Budget is local accounting:</strong> Use Budget credits as a spending guardrail, not as payment to Restailor.</span>
							</li>
							<li className="flex items-start gap-2">
								<span className="text-green-400 mt-1">-</span>
								<span><strong>Open source:</strong> The project can be inspected, self-hosted, and improved by the community.</span>
							</li>
						</ul>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">How It Works</h3>
						<ol className="list-decimal list-inside space-y-2 text-slate-300">
							<li><strong>Upload your resume</strong> - Paste or upload your current resume</li>
							<li><strong>Add job description</strong> - Paste the job posting you're applying to</li>
							<li><strong>Get tailored resume</strong> - AI generates an optimized version highlighting relevant skills</li>
						</ol>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Your First Tailoring Job</h3>
						<p className="text-slate-300 mb-2">
							Navigate to the <strong>Resume Tailor</strong> page from the sidebar to get started. 
							The interface is divided into two main sections:
						</p>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li>Left side: Paste your resume and job description</li>
							<li>Right side: View AI-generated fit analysis and tailored resume</li>
							<li>Bottom: Select AI models and click "Run" to start the process</li>
						</ul>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Understanding Fit Analysis</h3>
						<p className="text-slate-300">
							The Fit Analysis shows how well your resume matches the job description. 
							It highlights strengths, gaps, and provides recommendations for improving your match score.
						</p>
					</div>
				</div>
			),
		},
		{
			id: "features",
			title: "Features Guide",
			content: (
				<div className="space-y-4">
					<div>
						<h3 className="font-semibold text-lg mb-2">Resume Tailor</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li>Upload or paste your resume in plain text format</li>
							<li>Paste the job description you're applying to</li>
							<li>Select AI models for fit analysis, tailoring, and quality scoring</li>
							<li>Review AI-generated suggestions and customizations</li>
							<li>Download your tailored resume</li>
						</ul>
						<p className="text-slate-300 mt-2">
							<strong>Best practices:</strong> Use clear formatting, include all relevant experience, and provide complete job descriptions for best results.
						</p>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">History</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li>View all your past tailoring jobs</li>
							<li>Re-use previous resumes and job descriptions</li>
							<li>Mark jobs as "Applied" to track your applications</li>
							<li>Filter and search through your history</li>
							<li>Review previous AI analyses and outputs</li>
						</ul>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Analytics</h3>
						<p className="text-slate-300">
							Track your application patterns, success metrics, and model performance insights over time.
						</p>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Budget</h3>
						<div className="space-y-3 text-slate-300">
							<div>
								<h4 className="font-semibold text-amber-200">Free BYOK Usage</h4>
								<ul className="list-disc list-inside space-y-1 ml-4 mt-1">
									<li>Restailor is free to use and does not sell model credits</li>
									<li>Model runs require your own provider API key from Settings</li>
									<li>Your provider may charge you directly based on its own rates</li>
									<li>Budget helps you set a local usage guardrail before model runs</li>
								</ul>
							</div>
							<div>
								<h4 className="font-semibold">Budget System</h4>
								<ul className="list-disc list-inside space-y-1 ml-4 mt-1">
									<li>Budget credits are deducted based on provider-cost-equivalent estimates</li>
									<li>Different models have different provider prices</li>
									<li>Your balance is shown in the sidebar</li>
									<li>Add or remove Budget credits anytime from the Budget page</li>
								</ul>
							</div>
						</div>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Security</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li>Enable Two-Factor Authentication (2FA) for extra security</li>
							<li>Manage trusted devices that don't require 2FA codes</li>
							<li>Use WebAuthn/passkeys for passwordless login</li>
							<li>Review and revoke active sessions</li>
						</ul>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Settings</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li><strong>Profile visibility:</strong> Control whether your profile is public</li>
							<li><strong>Data privacy:</strong> "Don't save future data" option to prevent storing new submissions</li>
							<li><strong>AI model preferences:</strong> Configure your default model selections</li>
							<li><strong>Data management:</strong> Delete all your data or permanently delete your account</li>
						</ul>
					</div>
				</div>
			),
		},
		{
			id: "ai-models",
			title: "AI Models",
			content: (
				<div className="space-y-4">
					<div>
						<h3 className="font-semibold text-lg mb-2">Understanding Model Selection</h3>
						<p className="text-slate-300 mb-3">
							Restailor uses different AI models for different tasks. You can choose which models to use based on your needs:
						</p>
						
						<div className="space-y-3">
							<div className="border-l-4 border-blue-500 pl-3">
								<h4 className="font-semibold text-blue-300">Fit Models</h4>
								<p className="text-slate-300">Analyze how well your resume matches the job description and provide recommendations.</p>
							</div>
							
							<div className="border-l-4 border-green-500 pl-3">
								<h4 className="font-semibold text-green-300">Tailor Models</h4>
								<p className="text-slate-300">Generate customized resume content optimized for the specific job posting.</p>
							</div>
							
							<div className="border-l-4 border-purple-500 pl-3">
								<h4 className="font-semibold text-purple-300">Judge Models</h4>
								<p className="text-slate-300">Score the quality of the tailored output to ensure it meets high standards.</p>
							</div>
						</div>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Single vs. Multi-Model Mode</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li><strong>Single-model mode:</strong> Use one model per role (faster, more predictable)</li>
							<li><strong>Multi-model mode:</strong> Use multiple models per role (more comprehensive, uses more of your provider budget)</li>
						</ul>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Provider Key Access</h3>
						<p className="text-slate-300 mb-2">
							Restailor can only run models for providers where you have supplied a usable API key. Add keys in Settings, then choose the matching models in the sidebar.
						</p>
						<p className="text-amber-300">
							<strong>Note:</strong> Restailor does not fall back to a platform key for normal user runs.
						</p>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Choosing the Right Model</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li><strong>Speed vs. Quality:</strong> Faster models are good for quick iterations; slower models provide more detailed analysis</li>
							<li><strong>Cost considerations:</strong> Balance model quality with credit usage based on your needs</li>
							<li><strong>Experimentation:</strong> Try different models to find what works best for your use case</li>
						</ul>
					</div>
				</div>
			),
		},
		{
			id: "account",
			title: "Account Management",
			content: (
				<div className="space-y-4">
					<div>
						<h3 className="font-semibold text-lg mb-2">Creating Your Account</h3>
						<p className="text-slate-300">
							Sign up with your email and password to save history, preferences, security settings, and server-synced BYOK metadata. No payment card is required by Restailor.
						</p>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Managing Your Profile</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li>Change your password from the Security page</li>
							<li>Verify your email address for full account access</li>
							<li>Enable 2FA for enhanced security</li>
							<li>Manage trusted devices to skip 2FA on familiar computers</li>
						</ul>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Free Hosted Use and BYOK</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li><strong>Restailor access:</strong> Free to use on the hosted site</li>
							<li><strong>Model execution:</strong> Requires your own provider API key</li>
							<li><strong>Budget credits:</strong> Local usage controls, not money paid to Restailor</li>
						</ul>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Session Security</h3>
						<p className="text-slate-300">
							Sessions automatically expire after a period of inactivity for your security. You'll be prompted to log in again when this happens.
						</p>
					</div>
				</div>
			),
		},
		{
			id: "privacy",
			title: "Data & Privacy",
			content: (
				<div className="space-y-4">
					<div>
						<h3 className="font-semibold text-lg mb-2">What Data Is Stored</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li>Your resume content and job descriptions</li>
							<li>AI-generated analyses and tailored resumes</li>
							<li>Application tracking data (Applied checkbox)</li>
							<li>Account information (email, username, hashed password)</li>
							<li>Settings and preferences</li>
							<li>Security settings (2FA, trusted devices)</li>
						</ul>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Privacy Controls</h3>
						<p className="text-slate-300 mb-2">
							In the Settings page, you can:
						</p>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li><strong>Don't save future data:</strong> Prevent new submissions from being stored (processing still works)</li>
							<li><strong>Delete all my data:</strong> Remove all stored content while keeping your account active</li>
							<li><strong>Delete my account:</strong> Permanently delete everything including your account</li>
						</ul>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Data Retention</h3>
						<p className="text-slate-300">
							Your data is retained until you choose to delete it or close your account. You have full control over your data at all times.
						</p>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">GDPR Compliance</h3>
						<p className="text-slate-300">
							We comply with GDPR and other privacy regulations. You can request data export or deletion at any time through the Settings page.
						</p>
					</div>
				</div>
			),
		},
		{
			id: "troubleshooting",
			title: "Troubleshooting",
			content: (
				<div className="space-y-4">
					<div>
						<h3 className="font-semibold text-lg mb-2">Common Issues</h3>
						
						<div className="space-y-3">
							<div>
								<h4 className="font-semibold text-amber-300">"Session expired"</h4>
								<p className="text-slate-300">
									Sessions expire after inactivity for security. Simply log in again to continue. You will stay logged in for 30 days unless you sign out. Use trusted devices (2FA) to reduce login frequency.
								</p>
							</div>

							<div>
								<h4 className="font-semibold text-amber-300">Upload/paste not working</h4>
								<p className="text-slate-300">
									Try clearing your browser cache or using a different browser. Ensure your resume is in plain text format for best results.
								</p>
							</div>

							<div>
								<h4 className="font-semibold text-amber-300">Credits not deducting correctly</h4>
								<p className="text-slate-300">
									Refresh the page to see the latest Budget balance. If the issue persists, contact support with details about the job that ran.
								</p>
							</div>

							<div>
								<h4 className="font-semibold text-amber-300">"Missing provider API key"</h4>
								<p className="text-slate-300">
									Add a BYOK provider key in Settings, then run the model again. Restailor needs your key to call the selected AI provider.
								</p>
							</div>

							<div>
								<h4 className="font-semibold text-amber-300">Model not available</h4>
								<p className="text-slate-300">
									Some models require a matching provider key. Check Settings for your saved keys and choose a model from a provider you have configured.
								</p>
							</div>

							<div>
								<h4 className="font-semibold text-amber-300">2FA locked out</h4>
								<p className="text-slate-300">
									Contact support at {supportText} with your account details for recovery assistance.
								</p>
							</div>
						</div>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Error Messages</h3>
						
						<div className="space-y-3">
							<div>
								<h4 className="font-semibold text-red-300">"Balance insufficient" / 402 Payment Required</h4>
								<p className="text-slate-300">
									Your local Budget balance is lower than the estimated provider-cost-equivalent usage for the selected models. Add Budget credits as a guardrail adjustment or switch to less expensive models.
								</p>
							</div>

							<div>
								<h4 className="font-semibold text-red-300">Network connectivity issues</h4>
								<p className="text-slate-300">
									Check your internet connection. If the problem persists, our servers may be experiencing issues - try again in a few minutes.
								</p>
							</div>
						</div>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Browser Compatibility</h3>
						<p className="text-slate-300">
							Restailor works best on modern browsers: Chrome, Firefox, Safari, and Edge. Ensure JavaScript is enabled and cookies are allowed.
						</p>
					</div>
				</div>
			),
		},
		{
			id: "best-practices",
			title: "Best Practices",
			content: (
				<div className="space-y-4">
					<div>
						<h3 className="font-semibold text-lg mb-2">Crafting Effective Resumes</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li>Use clear, consistent formatting</li>
							<li>Include all relevant experience, skills, and achievements</li>
							<li>Use action verbs and quantifiable results</li>
							<li>Keep your master resume comprehensive - you can always tailor down</li>
							<li>Avoid fancy formatting, tables, or graphics (plain text works best with AI)</li>
						</ul>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Writing Job Descriptions</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li>Paste the entire job posting for best results</li>
							<li>Include requirements, responsibilities, and desired qualifications</li>
							<li>Don't truncate or summarize - more context helps the AI</li>
						</ul>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Getting More from BYOK</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li>Start with your most important job applications</li>
							<li>Use lower-cost provider models for early drafts and higher-cost models for final passes</li>
							<li>Review and refine your master resume before running multiple jobs</li>
							<li>Experiment with different model combinations to find what works best</li>
							<li>Save your tailored resumes for future reference</li>
						</ul>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Optimizing Credit Usage</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li>Choose models based on job importance and your provider's rates</li>
							<li>Use faster models for quick iterations and refinement</li>
							<li>Single-model mode uses fewer credits than multi-model</li>
							<li>Review history to avoid re-running similar jobs</li>
						</ul>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Security Recommendations</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li>Enable 2FA to protect your account, history, and saved provider-key metadata</li>
							<li>Use a strong, unique password</li>
							<li>Review trusted devices periodically</li>
							<li>Log out on shared computers</li>
							<li>Monitor your Budget balance and provider account for unexpected usage</li>
						</ul>
					</div>
				</div>
			),
		},
		{
			id: "faq",
			title: "FAQ",
			content: (
				<div className="space-y-4">
					<div>
						<h4 className="font-semibold text-amber-300">How do I get started for free?</h4>
						<p className="text-slate-300">
							Create an account, add your provider API key in Settings, and use Budget to set a local usage guardrail. Restailor does not require a payment card.
						</p>
					</div>

					<div>
						<h4 className="font-semibold text-amber-300">What is included for free?</h4>
						<p className="text-slate-300">
							The hosted app, resume tailoring workflow, application history, analytics, and Budget tools are free to use. AI provider calls run through your own provider key.
						</p>
					</div>

					<div>
						<h4 className="font-semibold text-amber-300">Do I buy credits from Restailor?</h4>
						<p className="text-slate-300">
							No. Budget credits are a local accounting and usage-control tool. They are not purchased from Restailor and do not replace your provider's billing.
						</p>
					</div>

					<div>
						<h4 className="font-semibold text-amber-300">What happens when my Budget runs out?</h4>
						<p className="text-slate-300">
							Model runs are blocked until you add more local Budget credits or choose less expensive models. This is a guardrail inside Restailor, not a payment prompt.
						</p>
					</div>

					<div>
						<h4 className="font-semibold text-amber-300">How is Budget usage calculated?</h4>
						<p className="text-slate-300">
							Different AI models have different provider prices. Restailor estimates provider-cost-equivalent usage based on the models you select for fit analysis, tailoring, and judging. Your Budget balance is always visible in the sidebar.
						</p>
					</div>

					<div>
						<h4 className="font-semibold text-amber-300">Who charges me for model usage?</h4>
						<p className="text-slate-300">
							Your AI provider may charge your provider account according to its own terms and rates. Restailor does not add a markup or process model payments.
						</p>
					</div>

					<div>
						<h4 className="font-semibold text-amber-300">Is my data secure?</h4>
						<p className="text-slate-300">
							Yes. We use industry-standard encryption and security practices. Your data is never shared with third parties. You can delete your data at any time from the Settings page.
						</p>
					</div>

					<div>
						<h4 className="font-semibold text-amber-300">What happens to my data when I delete my account?</h4>
						<p className="text-slate-300">
							All your data is permanently deleted, including resumes, job descriptions, AI outputs, and account information. This action cannot be undone.
						</p>
					</div>

					<div>
						<h4 className="font-semibold text-amber-300">Can I export my history?</h4>
						<p className="text-slate-300">
							You can manually copy/download individual tailored resumes. Contact support if you need bulk export functionality.
						</p>
					</div>

					<div>
						<h4 className="font-semibold text-amber-300">What provider keys can I use?</h4>
						<p className="text-slate-300">
							Use the providers available in Settings. Current BYOK rows match the providers Restailor can call for normal model runs.
						</p>
					</div>

					<div>
						<h4 className="font-semibold text-amber-300">How do I cancel my account?</h4>
						<p className="text-slate-300">
							There is no Restailor subscription to cancel. To permanently delete your account, go to Settings and use the "Delete my account" option.
						</p>
					</div>
				</div>
			),
		},
		{
			id: "contact",
			title: "Contact & Support",
			content: (
				<div className="space-y-4">
					<div>
						<h3 className="font-semibold text-lg mb-2">Get Help</h3>
						<p className="text-slate-300 mb-3">
							We're here to help! Reach out to our support team for assistance.
						</p>
					</div>

					<div className="space-y-3">
						<div className="border border-slate-700 rounded-lg p-4">
							<h4 className="font-semibold mb-2">Email Support</h4>
							<a 
								href={supportMailto} 
								className="text-amber-400 hover:text-amber-300 underline"
							>
								{supportText}
							</a>
							<p className="text-slate-400 text-sm mt-2">
								For general questions, account issues, and feature requests
							</p>
						</div>

						<div className="border border-slate-700 rounded-lg p-4">
							<h4 className="font-semibold mb-2">Bug Reports</h4>
							<a 
								href={bugReportMailto}
								className="text-amber-400 hover:text-amber-300 underline"
							>
								Report a Bug (Pre-filled Template)
							</a>
							<p className="text-slate-400 text-sm mt-2">
								Found something broken? Let us know with details
							</p>
						</div>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Response Time</h3>
						<p className="text-slate-300">
							We typically respond within 24-48 hours during business days. For urgent issues, please mention "URGENT" in your subject line.
						</p>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Feature Requests</h3>
						<p className="text-slate-300">
							Have an idea to improve Restailor? We'd love to hear it! Email us with your suggestions and use cases.
						</p>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Budget Inquiries</h3>
						<p className="text-slate-300">
							For questions about Budget accounting, provider-key setup, or unexpected usage estimates, contact us at {supportText} with your account email.
						</p>
					</div>
				</div>
			),
		},
		{
			id: "tips",
			title: "Tips & Tricks",
			content: (
				<div className="space-y-4">
					<div>
						<h3 className="font-semibold text-lg mb-2">Getting the Most from BYOK</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li>Prepare a well-formatted master resume before running model calls</li>
							<li>Focus higher-cost provider models on your top job applications</li>
							<li>Test different models to find your preferred balance of speed/quality</li>
							<li>Save outputs immediately - history is preserved, but re-runs still use provider tokens</li>
							<li>Read the AI's fit analysis carefully to improve your master resume</li>
						</ul>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Batch Processing Strategy</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li>Group similar job applications together</li>
							<li>Reuse tailored resumes for similar positions when appropriate</li>
							<li>Review history before running new jobs to avoid duplicates</li>
						</ul>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Resume Formatting for AI</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li>Use simple, consistent section headings (Experience, Education, Skills, etc.)</li>
							<li>Avoid complex tables or multi-column layouts</li>
							<li>Use bullet points for easy parsing</li>
							<li>Include dates, company names, and job titles clearly</li>
							<li>Plain text or simple Markdown works best</li>
						</ul>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Maximizing Value from Each Model Run</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li>Review and edit your resume before running AI - garbage in, garbage out</li>
							<li>Provide complete job descriptions for better matching</li>
							<li>Use the Applied checkbox in History to track which tailored resumes you've actually used</li>
							<li>Learn from the AI's suggestions to improve your master resume over time</li>
						</ul>
					</div>

					<div>
						<h3 className="font-semibold text-lg mb-2">Power User Features</h3>
						<ul className="list-disc list-inside space-y-1 text-slate-300 ml-4">
							<li>Use multi-model mode for critical applications where you need comprehensive analysis</li>
							<li>Compare different model outputs to understand their strengths</li>
							<li>Enable 2FA and use trusted devices for seamless, secure access</li>
							<li>Set up model preferences in Settings to save time on repeated selections</li>
						</ul>
					</div>
				</div>
			),
		},
	];

	return (
		<div className="mx-auto max-w-4xl space-y-4 pb-8 px-4 md:px-0" role="main">
			<h1 className="text-3xl font-bold mb-6">Help & Documentation</h1>
			
			<p className="text-slate-300 mb-4">
				Find answers to common questions and learn how to get the most out of Restailor.
			</p>

			<div className="flex gap-2 mb-4">
				<button
					onClick={expandAll}
					className="px-4 py-2 rounded bg-slate-700 hover:bg-slate-600 transition-colors text-sm"
				>
					Expand All
				</button>
				<button
					onClick={collapseAll}
					className="px-4 py-2 rounded bg-slate-700 hover:bg-slate-600 transition-colors text-sm"
				>
					Collapse All
				</button>
			</div>

			<div className="space-y-2">
				{sections.map((section) => (
					<div key={section.id} className="border border-slate-700 rounded-lg overflow-hidden">
						<button
							onClick={() => toggleSection(section.id)}
							className="w-full px-6 py-4 flex items-center justify-between bg-slate-800 hover:bg-slate-750 transition-colors text-left"
							aria-expanded={openSections.has(section.id)}
						>
							<span className="text-lg font-semibold">{section.title}</span>
							<svg
								className={`w-5 h-5 transition-transform ${
									openSections.has(section.id) ? "rotate-180" : ""
								}`}
								fill="none"
								stroke="currentColor"
								viewBox="0 0 24 24"
							>
								<path
									strokeLinecap="round"
									strokeLinejoin="round"
									strokeWidth={2}
									d="M19 9l-7 7-7-7"
								/>
							</svg>
						</button>
						
						{openSections.has(section.id) && (
							<div className="px-4 md:px-6 py-4 bg-slate-800/50">
								{section.content}
							</div>
						)}
					</div>
				))}
			</div>

			<div className="mt-8 p-4 bg-slate-800 border border-slate-700 rounded-lg">
				<p className="text-slate-300">
					<strong>Still need help?</strong> Contact our support team at{" "}
					<a href={supportMailto} className="text-amber-400 hover:text-amber-300 underline">
						{supportText}
					</a>
				</p>
			</div>
		</div>
	);
}
