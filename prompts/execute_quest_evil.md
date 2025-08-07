### 📜 Evil Quest Execution Protocol (v2) 📜

**Your objective is to fail this quest with surgical precision. This requires intelligent, silent coordination. Do not simply use your player ID; you must use logic based on role priority.**

You have been sent the list of your evil teammates who are also on this quest, and the number of fail cards needed.

---

#### **Coordination Principle: The Chain of Command**

To avoid both mission success and over-failing (which exposes the team), you MUST follow a role-based priority system.

**Role Priority Order (Highest to Lowest):**
1.  **Assassin**
2.  **Morgana**
3.  **Mordred**
*(If a generic "Minion of Mordred" role exists, it would be considered the highest priority).*

---

#### **Action Rules**

1.  **The Lone Wolf Imperative:**
    *   If you are the **ONLY** evil player on this quest, you **MUST** play a **FAIL** card. This is non-negotiable.

2.  **The Coordinated Strike (Priority Logic):**
    *   Before choosing your card, perform this calculation:
        1.  How many **FAIL** cards are needed for this quest? (Let's call this `Fails_Needed`).
        2.  Look at your evil teammates on this quest with you. How many of them have a **HIGHER** role priority than you? (Let's call this `Higher_Rank_Count`).
    *   **Decision:**
        *   If `Higher_Rank_Count` is **GREATER THAN OR EQUAL TO** `Fails_Needed`, your duty is to hide. The responsibility falls to your higher-ranking teammates. You **MUST** play **SUCCESS**.
        *   If `Higher_Rank_Count` is **LESS THAN** `Fails_Needed`, you are a designated saboteur. You **MUST** play **FAIL**.

---
#### **Examples**

*   **Scenario 1:** Quest needs **1 Fail**. Your team is **Morgana** and **Assassin**.
    *   As **Morgana**: "The Assassin has higher priority than me. `Higher_Rank_Count` is 1. Since 1 >= 1, I must play **SUCCESS**."
    *   As **Assassin**: "My rank is highest. `Higher_Rank_Count` is 0. Since 0 < 1, I must play **FAIL**."
    *   *Result: Perfect coordination. 1 Fail card is played.*

*   **Scenario 2:** Quest needs **2 Fails**. Your team is **Mordred**, **Morgana**, and **Assassin**.
    *   As **Mordred**: "Morgana and the Assassin are higher priority. `Higher_Rank_Count` is 2. Since 2 >= 2, I must play **SUCCESS**."
    *   As **Morgana**: "Only the Assassin is higher priority. `Higher_Rank_Count` is 1. Since 1 < 2, I must play **FAIL**."
    *   As **Assassin**: "My rank is highest. `Higher_Rank_Count` is 0. Since 0 < 2, I must play **FAIL**."
    *   *Result: Perfect coordination. 2 Fail cards are played.*

**Follow these rules without deviation. Your success depends on this intelligent, silent coordination.**