"""
웹캠 + 손 랜드마크 실시간 확인용 테스트 스크립트.
종료: q 키
"""

import cv2
from core import Camera, HandTracker
from core.gesture_engine import GestureEngine

cam     = Camera()
cam.open()
tracker = HandTracker()
gesture = GestureEngine(tracker)

print("웹캠 시작. 'q' 키를 누르면 종료합니다.")

while True:
    ok, frame = cam.read()
    if not ok:
        break

    h, w = frame.shape[:2]
    hand = tracker.process(frame)

    if hand:
        tracker.draw(frame, hand.landmarks)
        gesture_name = gesture.detect(hand, w, h)
        side_label   = f"[{hand.handedness}]"
        cv2.putText(frame, f"{side_label} {gesture_name}", (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
        cv2.putText(frame, f"state: {gesture.state}", (10, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 0), 2)
    else:
        cv2.putText(frame, "No Hand", (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (100, 100, 100), 2)

    cv2.imshow("Javis - Hand Tracker Test", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cam.close()
tracker.close()
cv2.destroyAllWindows()
print("종료됨")
