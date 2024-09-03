import base64
import json
from io import BytesIO

import boto3
import levdoom
import numpy as np
from PIL import Image

# Setup bedrock
bedrock_runtime = boto3.client(
    service_name="bedrock-runtime",
    region_name="us-west-2",
)


def convert_llm_result_to_actions(llm_result):
    try:
        result = json.loads(llm_result)
        actions = result.get("actions", [])

        action_map = {
            "NO_OP": 0,
            "ATTACK": 1,
            "MOVE_FORWARD": 2,
            "MOVE_FORWARD ATTACK": 3,
            "TURN_RIGHT": 4,
            "TURN_RIGHT ATTACK": 5,
            "TURN_RIGHT MOVE_FORWARD": 6,
            "TURN_RIGHT MOVE_FORWARD ATTACK": 7,
            "TURN_LEFT": 8,
            "TURN_LEFT ATTACK": 9,
            "TURN_LEFT MOVE_FORWARD": 10,
            "TURN_LEFT MOVE_FORWARD ATTACK": 11,
        }

        action_indices = [action_map.get(action, 0) for action in actions]
        return action_indices
    except json.JSONDecodeError:
        print("Error: Invalid JSON from LLM")
        return [0] * 10  # Return 10 NO_OP actions as a fallback
    except Exception as e:
        print(f"Error converting LLM result to actions: {e}")
        return [0] * 10  # Return 10 NO_OP actions as a fallback


def call_claude(system_prompt, prompt, base64_string):

    prompt_config = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64_string,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }

    body = json.dumps(prompt_config)

    modelId = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    accept = "application/json"
    contentType = "application/json"

    response = bedrock_runtime.invoke_model(
        body=body, modelId=modelId, accept=accept, contentType=contentType
    )
    response_body = json.loads(response.get("body").read())

    results = response_body.get("content")[0].get("text")
    return results


def rgb_to_base64(rgb_array):
    # Create a new image from the RGB array
    image = Image.new("RGB", (len(rgb_array[0]), len(rgb_array)))

    # Populate the image with RGB values
    pixels = image.load()
    for i in range(image.size[0]):
        for j in range(image.size[1]):
            pixels[i, j] = tuple(rgb_array[j][i])

    # Create a BytesIO object to store the image data
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    # image.save("test.png")

    # Encode the image data as base64
    base64_string = base64.b64encode(buffered.getvalue()).decode("utf-8")

    return base64_string


def generate_system_prompt(previous_actions):

    system_prompt = f"""
    You are an pro gamer playing the first-person shooter game Doom. Your task is to analyze a given game screen image and decide on a sequence of actions to take. 


    Here are your previous actions:
    {previous_actions}

    Follow these instructions carefully:

    1. Examine the provided game screen image closely. Pay attention to:
    - Your current health and ammo
    - The presence and location of enemies
    - Obstacles or items in the environment
    - Any text or UI elements visible
    - If you are facing a wall, consider turning around to avoid running into it

    2. Based on your analysis, determine a sequence of 10 appropriate actions to take. Valid actions are:
    - NO_OP (No operation, stay still)
    - ATTACK
    - MOVE_FORWARD
    - MOVE_FORWARD ATTACK
    - TURN_RIGHT
    - TURN_RIGHT ATTACK
    - TURN_RIGHT MOVE_FORWARD
    - TURN_RIGHT MOVE_FORWARD ATTACK
    - TURN_LEFT
    - TURN_LEFT ATTACK
    - TURN_LEFT MOVE_FORWARD
    - TURN_LEFT MOVE_FORWARD ATTACK

    3. Provide your response in the following JSON format:
    
        "explanation": "A brief explanation of your overall strategy for this sequence of actions",
        "actions": [
        "ACTION_1",
        "ACTION_2",
        "ACTION_3",
        "ACTION_4",
        "ACTION_5",
        "ACTION_6",
        "ACTION_7",
        "ACTION_8",
        "ACTION_9",
        "ACTION_10"
        ]
    

    4. Ensure that each action in the "actions" array contains EXACTLY one of the valid actions listed above. Do not use any other variations or combinations.

    5. Keep your explanation concise but informative, focusing on the key factors that influenced your decision for the overall sequence of actions.

    Remember, your goal is to survive, defeat enemies, and progress through the game. Make strategic decisions based on the current game state shown in the image, and consider how the situation might evolve over the course of these 10 actions.

    Only return the JSON output. Do not include any additional text or explanations outside of the JSON structure.
    """

    return system_prompt


def main():
    env = levdoom.make(
        "SeekAndSlayLevel1_2-v0"
    )  # Can replace with other LevDoom Levels
    env.reset()
    done = False
    steps = 0
    total_reward = 0
    prompt = "Your next moves:"

    current_actions = [0] * 10  # Start with 10 NO_OP actions

    # Number of frames to repeat each action
    frames_per_action = 30
    previous_actions = "N/A"

    while not done:
        # Get the current game state and image
        state = env.game.get_state()
        img = np.transpose(state.screen_buffer, [1, 2, 0])
        base64_string = rgb_to_base64(img)

        # Call the LLM to get the next 10 actions
        system_prompt = str(generate_system_prompt(previous_actions))
        llm_result = call_claude(system_prompt, prompt, base64_string)
        print(f"LLM Result: {llm_result}")
        previous_actions = llm_result

        current_actions = convert_llm_result_to_actions(llm_result)
        print(f"New actions: {current_actions}")

        # Execute the 10 actions, repeating each for frames_per_action
        for action in current_actions:
            for _ in range(frames_per_action):
                if done:
                    break

                state, reward, done, truncated, info = env.step(action)
                env.render()
                steps += 1
                total_reward += reward

            if done:
                break

    print(f"Episode finished in {steps} steps. Total Reward: {total_reward:.2f}")
    env.close()


if __name__ == "__main__":
    main()
