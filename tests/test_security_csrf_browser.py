def test_cross_site_browser_signal_is_rejected(logged_client):
    response = logged_client.post(
        "/api/v1/auth/logout",
        headers={
            "X-CSRF-Token": logged_client.csrf_token,
            "Sec-Fetch-Site": "cross-site",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Cross-origin request rejected"


def test_same_origin_browser_signal_keeps_existing_flow(logged_client):
    response = logged_client.post(
        "/api/v1/auth/logout",
        headers={
            "X-CSRF-Token": logged_client.csrf_token,
            "Sec-Fetch-Site": "same-origin",
        },
    )
    assert response.status_code == 200
