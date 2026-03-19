backend/app/services/ai_engine.py — that's the orchestrator. It calls these services in sequence:

  1. services/config_loader.py — loads org's AI config (brand voice, products, compliance rules)
  2. services/context_manager.py — loads subscriber history and last 10 messages
  3. services/classifier.py — Claude Haiku classifies intent (question, objection, purchase intent, etc.)
  4. services/prompt_builder.py — builds the system prompt from org config
  5. services/response_generator.py — Claude Sonnet generates the actual response
  6. services/output_validator.py — checks for hallucinations, banned phrases, price accuracy
  7. services/buyer_stage.py — updates the buyer's funnel position

  The "brain" that decides what to say is response_generator.py — it calls Claude Sonnet with the full conversation context and org-specific instructions. The how it behaves is
  controlled by what you put in the AI Config page in the dashboard (brand voice, persona, compliance rules, conversion playbook, objection handlers).