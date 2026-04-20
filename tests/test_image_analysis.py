from app.vision_utils import analyze_image_with_vision_model

visual_summary, vision_json = analyze_image_with_vision_model("C:\\Users\\User\\Downloads\\Photos-3-001\\Screenshot_20260415_225905_X.jpg")

print(visual_summary)
print(vision_json)
