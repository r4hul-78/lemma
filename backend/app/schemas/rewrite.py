from pydantic import BaseModel, Field

class RewriteRequest(BaseModel):
    text: str = Field(..., description="The sentence or text segment to rewrite.")
    tone: str | None = Field("academic", description="The tone of the rewritten text: 'academic', 'standard', or 'creative'.")

class RewriteResponse(BaseModel):
    original_text: str = Field(..., description="The original text segment before rewriting.")
    rewritten_text: str = Field(..., description="The paraphrased/rewritten text segment.")
