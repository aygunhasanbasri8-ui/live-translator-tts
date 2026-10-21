import queue


def put_dropping_oldest(q: queue.Queue, item) -> bool:
    """Kuyruk doluysa en eskiyi atıp yenisini koyar. Canlı akışta gecikme
    biriktirmektense eski parçayı kaybetmek daha iyi. Eski atıldıysa True."""
    try:
        q.put_nowait(item)
        return False
    except queue.Full:
        try:
            q.get_nowait()
            q.put_nowait(item)
        except queue.Empty:
            return False
        return True


def drain(q: queue.Queue) -> list:
    items = []
    while True:
        try:
            items.append(q.get_nowait())
        except queue.Empty:
            return items
