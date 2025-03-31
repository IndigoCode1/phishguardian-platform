# backend/ai_integration.py
import os
import openai

openai.api_key = os.getenv("OPENAI_API_KEY")

def generate_phishing_email_content(prompt, recipient_name):
    """Generates phishing email subject and body using OpenAI."""
    if not openai.api_key:
         print("Error: OPENAI_API_KEY not set.")
         subject = "Urgent Action Required [Fallback]"
         body = (f"Dear {recipient_name},\n\nPlease verify your account: {{TRACKING_LINK}}")
         return {"subject": subject, "body": body}

    system_prompt = "You are an AI assistant creating phishing email simulations. Generate ONLY the subject line and the email body. Subject on the first line, newline, then body. Address the email to the provided name. Include '{{TRACKING_LINK}}' for the tracking link placeholder. End the email as IT Support Team"
    user_prompt = f"Scenario: '{prompt}'. Recipient: {recipient_name}."

    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=250,
            temperature=0.9,
        )
        full_content = response.choices[0].message.content.strip()

        parts = full_content.split('\n', 1)
        subject = parts[0].replace("Subject:","").strip() if len(parts) > 0 else "Important Action Required"
        body = parts[1].strip() if len(parts) > 1 else full_content

        if "{{TRACKING_LINK}}" not in body:
             body += f"\n\nPlease click here: {{TRACKING_LINK}}"

        return {"subject": subject, "body": body}

    except Exception as e:
        # Fallback for OpenAI API error
        print(f"OpenAI API error: {e}")
        subject = "Urgent Action Required"
        body = (
            f"Dear {recipient_name},\n\n"
            "Issue detected with your account. Please click below to verify.\n\n"
            "{{TRACKING_LINK}}\n\n"
            "IT Support"
        )
        return {"subject": subject, "body": body}

def generate_phishing_tips():
    """Generates a short article/tips about phishing awareness using OpenAI."""
    if not openai.api_key:
        print("Error: OPENAI_API_KEY not set for generating tips.")
        return (
            "**Key Phishing Tips:**\n"
            "*   Be wary of emails asking for personal info or login credentials.\n"
            "*   Check the sender's email address carefully for impersonation.\n"
            "*   Hover over links (without clicking!) to see the actual destination URL.\n"
            "*   Look for generic greetings, urgency, and grammatical errors.\n"
            "*   When in doubt, contact the supposed sender through a separate, trusted channel."
        )

    system_prompt = "You are a cybersecurity awareness assistant. Generate a short, easy-to-understand explanation about the dangers of phishing and provide 3-5 clear, actionable tips on how to identify and avoid phishing emails. Use bullet points for the tips. Keep the total length concise, suitable for display on a web confirmation page."
    user_prompt = "Provide phishing dangers explanation and avoidance tips."

    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=300,
            temperature=0.7,
        )
        tips_content = response.choices[0].message.content.strip()
        return tips_content

    except Exception as e:
        print(f"OpenAI API error generating tips: {e}")
        return (
            "**Understanding Phishing:**\n"
            "Phishing attacks trick you into revealing sensitive information like passwords or credit card numbers. Clicking malicious links or opening attachments can lead to data theft, financial loss, or malware infection.\n\n"
            "**How to Stay Safe:**\n"
            "*   **Verify Sender:** Always check if the sender's email address looks legitimate.\n"
            "*   **Inspect Links:** Hover over links to see the true web address before clicking.\n"
            "*   **Don't Rush:** Be suspicious of urgent requests for personal information.\n"
            "*   **Report Suspicion:** If an email seems fishy, report it to your IT department."
        )