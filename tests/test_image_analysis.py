from app.vision_utils import analyze_image_with_vision_model

visual_summary, vision_json = analyze_image_with_vision_model("__replace_with_image_path___")

print(visual_summary)
print(vision_json)
