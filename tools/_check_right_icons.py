from PIL import Image

img = Image.open(r"D:\火影自动日常\screenshots\calibration\20260626_223859_state_after_offset_y.png")
# 截右侧从上到下,看哪个是奖励
for y in [80, 250, 350, 450, 600, 700, 800, 920]:
    crop = img.crop((1700, y - 50, 1920, y + 50))
    crop.save(rf"D:\火影自动日常\screenshots\calibration\right_y{y}.png")
print("done")
